
from mech.fusion.avm2 import (assembler, constants,
                              instructions, abc_ as abc,
                              traits, util)

from itertools import chain

class WrongContextError(BaseException):
    def __init__(self, got, expected):
        self.got, self.expected = got, expected

    def __str__(self):
        return ("You called %r while the current context was"
                " a %s context." % (self.got, self.expected))

class GlobalContext(object):
    CONTEXT_TYPE = "global"
    parent = None

    def __init__(self, gen):
        self.gen = gen

    def exit(self):
        return None
        
    def new_script(self):
        ctx = ScriptContext(self.gen, self)
        self.gen.enter_context(ctx)
        return ctx

class _MethodContextMixin(object):
    """
    A mixin providing method factories for things like
    classes and scripts.
    """
    def new_method_info(self, name, params, rettype):
        """
        An internal function for generating an AbcMethodInfo
        with the given name, parameters, and return type.
        """
        return abc.AbcMethodInfo(name,
                                 [self.gen._get_type(t) for t, n in params],
                                 self.gen._get_type(rettype),
                                 param_names=[n for t, n in params])
    
    def new_method(self, name, params=None, rettype=None, kind="method", static=False, override=False):
        """
        Create a new method with the name "name" and parameter list "arglist" and
        return type "returntype".

        The "name" parameter should be a string or an object with a multiname()
        method for converting to an ABC Multiname (QName, TypeName, Multiname,
        Name, etc). A common use is to use a QName with the ns being a private,
        protected or public namespace for access protection.

        "arglist" should be an iterable of (type, name) pairs, with the "name"
        being a string and "type" being an object with a multiname() method for
        specifying the type of the parameter.

        "returntype" should be the same kind of "type" parameter.

        "kind" is the type of method. It can either be "method", "getter", or "setter". If
        it is a getter, it must have a non-void return type and no argument list. If it is
        a setter, it must have a void return type and must take one argument.

        "static" determines whether to add the function to the static or instance
        traits of the class. For a script, this parameter will do nothing.

        "override" has to be set if you attempt to override a method in the
        superclass, including ones from the native Flash Player API.
        """
        params = params or []
        name = self.gen._get_type(name)
        meth = self.new_method_info(str(name), params, rettype or constants.QName("void"))
        KIND = dict(method=traits.AbcMethodTrait,
                    getter=traits.AbcGetterTrait,
                    setter=traits.AbcSetterTrait)
        trait = KIND.get(kind, kind)(name, meth, override=override)
        if static:
            self.add_static_trait(trait)
        else:
            self.add_instance_trait(trait)
        ctx = MethodContext(self.gen, meth, self, params)
        self.gen.enter_context(ctx)
        return ctx

class ScriptContext(_MethodContextMixin):
    CONTEXT_TYPE = "script"

    def __init__(self, gen, parent):
        self.name = "script"
        self.gen, self.parent = gen, parent
        self.init = None
        self.traits = []
        self.pending_classes = {}
        self.pending_classes_order = []
        self.done = False
    
    def make_init(self):
        """
        Create a script init method and enter the context
        for generating code on that method.
        """
        if not self.init:
            self.init = abc.AbcMethodInfo("", [], constants.ANY_NAME)
            self.init.ctx = MethodContext(self.gen, self.init, self, [])
        self.gen.enter_context(self.init.ctx)
        return self.init.ctx
    
    def new_class(self, name, super_name=None, bases=None):
        """
        Create a new class and enter the context for that class.
        
        This will generate both the AbcInstance and the AbcClass.

        The "name" parameter should be an object with a multiname() method for
        converting to an ABC Multiname (QName, TypeName, Multiname, Name, etc).
        A common use is to use a QName with the ns being a private, protected or
        public namespace for access protection.
        """
        # allow hardcoded bases
        if name in self.pending_classes:
            # XXX
            ctx, _ = self.pending_classes[name]
            self.gen.enter_context(ctx)
            return ctx
        ctx = ClassContext(self.gen, name, super_name, self)
        self.pending_classes[name] = (ctx, bases)
        self.pending_classes_order.append(name)
        self.gen.enter_context(ctx)
        return ctx

    def add_trait(self, trait):
        """
        Add a trait to this script, usually used for adding classes,
        script-level variables (slots), and methods.
        """
        self.traits.append(trait)

    add_static_trait = add_trait
    add_instance_trait = add_trait

    def exit(self):
        if self.done:
            return self.parent

        self.done = True
        meth = self.make_init()

        insts = []

        if meth.asm.instructions[2:]:
            insts = meth.asm.instructions[2:]
            meth.asm.instructions = meth.asm.instructions[:2]

        for key in self.pending_classes_order:
            context, parents = self.pending_classes[key]
            if parents is None:
                parents = []
                ctx = self.gen._get_class_context(context.super_name, self.pending_classes)
                while ctx:
                    parents.append(ctx.name)
                    ctx = self.gen._get_class_context(ctx.super_name, self.pending_classes)

                if not constants.QName("Object") in parents:
                    parents.append(constants.QName("Object"))

            self.gen.I(instructions.getscopeobject(0))

            for parent in reversed(parents):
                self.gen.I(instructions.getlex(parent),
                           instructions.pushscope())
            
            self.traits.append(traits.AbcClassTrait(context.name,
                                                    context.classobj))
            self.gen.I(instructions.getlex(context.super_name))
            self.gen.I(instructions.newclass(context.index))
            self.gen.I(*[instructions.popscope()]*len(parents))
            self.gen.I(instructions.initproperty(context.name))
        
        self.gen.abc.scripts.index_for(abc.AbcScriptInfo(self.init,
                                                         self.traits))
        self.gen.exit_context()
        meth.asm.instructions += insts
        return self.parent

class ClassContext(_MethodContextMixin):
    CONTEXT_TYPE = "class"

    def __init__(self, gen, name, super_name, parent):
        self.gen = gen
        self.name = name
        self.super_name = super_name or constants.QName("Object")
        self.parent = parent
        self.instance_traits = []
        self.static_traits   = []
        self.cinit = None
        self.iinit = None

    def make_cinit(self):
        """
        Create a cinit (class initializer) method used to set up static
        traits and variables, and enter the correct context to generate
        code on it.

        cinits are usually called when the first instance of a class is
        created, although it is sometimes called when the "newclass" opcode
        is run.
        """
        if not self.cinit:
            self.cinit = abc.AbcMethodInfo("", [], constants.ANY_NAME)
            self.cinit.ctx = MethodContext(self.gen, self.cinit, self, [])
        self.gen.enter_context(self.cinit.ctx)
        return self.cinit.ctx

    def make_iinit(self, params=None):
        """
        Create a iinit (instance initializer) method used to set up instance
        variables, and enter the correct context to generate code on it.

        iinits are always called when an instance of a class is created using
        the "new" operator in ECMAScript, which translates into the "constructprop"
        opcode in ABC.
        """
        params = params or ()
        if self.iinit:
            if params:
                raise ValueError("parameters cannot be redefined")
        else:
            self.iinit = self.new_method_info("", params, constants.QName("void"))
            self.iinit.ctx = MethodContext(self.gen, self.iinit, self, [])
            self.iinit.ctx.constructor = True
        
        self.gen.enter_context(self.iinit.ctx)

        if not self.iinit.done:
            self.gen.push_this()
            self.gen.emit("constructsuper", 0)

    def add_instance_trait(self, trait):
        """
        Add an instance-level trait. Traits are not only used for
        instance variables (slots) but also used for method declarations.
        """
        self.instance_traits.append(trait)
        return len(self.instance_traits)

    def add_static_trait(self, trait):
        """
        Add a static-level trait. Traits are not only used for
        instance variables (slots) but also used for method declarations.
        """
        self.static_traits.append(trait)
        return len(self.static_traits)
    
    def exit(self):
        assert self.parent.CONTEXT_TYPE == "script"
        if self.iinit is None:
            self.make_iinit()
            self.gen.exit_context()
        if self.cinit is None:
            self.make_cinit()
            self.gen.exit_context()
        self.instance = abc.AbcInstanceInfo(self.name, self.iinit,
                                            traits=self.instance_traits,
                                            super_name=self.super_name)
        self.classobj = abc.AbcClassInfo(self.cinit, traits=self.static_traits)
        self.index = self.gen.abc.instances.index_for(self.instance)
        self.gen.abc.classes.index_for(self.classobj)
        return self.parent
        
class MethodContext(object):
    CONTEXT_TYPE = "method"
    scope_nest   = 0
    constructor  = False

    def __init__(self, gen, method, parent, params, stdprologue=True):
        self.gen, self.method, self.parent = gen, method, parent
        param_names = [n for t, n in params]
        self.asm = assembler.Avm2CodeAssembler(gen.constants,
                                               ['this']+param_names)
        self.acv_traits = []
        self.exceptions = []
        if stdprologue:
            self.restore_scopes()
    
    def exit(self):
        if self.method.done:
            return self.parent

        self.method.done = True
        self.gen.abc.methods.index_for(self.method)
        self.gen.abc.bodies.index_for(abc.AbcMethodBodyInfo(
                self.method, self.asm, self.acv_traits, self.exceptions))
        return self.parent

    def add_activation_trait(self, trait):
        """
        Add activation traits, or traits on the activation object.
        
        This is used to implement some core concepts in ECMAScript,
        like the function-as-class semantics between calling a function
        and constructing an instance of a function. When you construct
        an instance of a function, a new activation object is created,
        and is referenced by the "this" parameter, which would normally
        reference the calling function.
        """
        self.acv_traits.append(trait)
        return len(self.acv_traits)

    def add_exception(self, param_type):
        """
        This is an internal method made to add AbcExceptions to a method.

        It uses -1 for from, to, and target values, which should be filled
        in by the bogus addexcinfo, begintry, and endtry "instructions".
        """
        exc = abc.AbcException(-1, -1, -1, param_type, "")
        self.asm.add_instruction(instructions.addexcinfo(self, exc))
        self.exceptions.append(exc)
        return len(self.exceptions)-1
    
    def add_instructions(self, *i):
        """
        Add one or more instructions to this method.
        """
        self.asm.add_instructions(*i)
    
    @property
    def next_free_local(self):
        """
        The next free local variable (register).
        """
        return self.asm.next_free_local

    def set_local(self, name):
        """
        Symbollically set a local as "used" and return the index that
        it was stored at. This does not produce a "setlocal" opcode,
        please use the generator interface for this.
        """
        return self.asm.set_local(name)

    def kill_local(self, name):
        """
        Symbollically set a local as "empty" and return the index of
        the freed local. Thisdoes not produce a "kill" opcode,
        please use the generator interface for this.
        """
        return self.asm.kill_local(name)

    def get_local(self, name):
        """
        Get the index for the local/register identified with "name".
        """
        return self.asm.get_local(name)

    def has_local(self, name):
        """
        Return True if there is a local/register identified with "name".
        """
        return self.asm.has_local(name)

    def restore_scopes(self):
        """
        Restore the scope stack.
        """
        self.asm.add_instruction(instructions.getlocal(self.scope_nest))
        self.asm.add_instruction(instructions.pushscope())

class CatchContext(object):
    # This is supposed to be a transparent context.
    def __init__(self, gen, parent):
        self.gen = gen
        self.parent = parent
        self.scope_nest = parent.scope_nest + 1
        self.local = "MF::ExceptionLocal%d" % (self.scope_nest,)

    def __getattr__(self, name):
        return getattr(self.parent, name)

    def restore_scopes(self):
        self.parent.restore_scores()
        self.gen.GL(self.local)
        self.gen.emit("pushscope")

    def exit(self):
        return self.parent

class Avm2ilasm(object):
    """ AVM2 'assembler' generator routines """
    def __init__(self, abc_=None, make_script=True):
        self.abc = abc_ or abc.AbcFile()
        self.constants = self.abc.constants
        self.context = GlobalContext(self)
        if make_script:
            self.script0 = self.context.new_script()

    def _get_type(self, TYPE):
        """
        An internal function designed to get a QName for
        a special construct of a "TYPE"
        """
        if getattr(TYPE, "multiname", None):
            return TYPE.multiname()
        if isinstance(TYPE, str):
            return constants.QName(TYPE)
        return TYPE

    def _get_class_context(self, name, DICT):
        """
        An internal function designed to get a certain
        class context for a name and a fallback dict.

        This is going used with some pending playerglobal
        parsing code that will automatically resolve base
        classes and push them onto the scope stack.
        """
        return DICT.get(name, [None])[0]

    def I(self, *i):
        """
        Add the instructions to the current method.
        """
        self.context.add_instructions(i)

    def SL(self, name):
        """
        Pop a value off the stack and set it in the local
        occupied to "name"
        """
        index = self.context.set_local(name)
        self.I(instructions.setlocal(index))
        return index

    def GL(self, name):
        """
        Get the local occupied to "name" and push it to the stack.
        """
        index = self.context.get_local(name)
        self.I(instructions.getlocal(index))
        return index

    def KL(self, name):
        """
        Kill the local currently occupied to "name"
        """
        index = self.context.kill_local(name)
        self.I(instructions.kill(index))

    def HL(self, name):
        """
        Return True if there is a local by the name of "name".
        """
        return self.context.has_local(name)

    def begin_class(self, name, super_name=None, bases=None):
        """
        Create a new class with the name "name" and superclass "super_name" and
        enter a context created for it.

        If you are inheriting a Flash Player class, currently you need to
        specify all of the baseclasses that should be on the scope stack,
        excluding "Object", through a list of objects with a multiname()
        method which returns a appropriate QName (QName implements this itself).
        This restriction should go away soon, hopefully.
        
        The "name" and "super_name" parameters should be an object with a
        multiname() method for converting to an ABC Multiname (QName, TypeName,
        Multiname, Name, etc). A common use is to use a QName with the ns being
        a PackageNamespace for packaging classes as found in AS3 and Java. This
        use case is so common that the constants module has a special function
        for making these types of QNames: packagedQName, as used like:

          packagedQName("flash.display", "Sprite")
        """
        return self.context.new_class(name, super_name, bases)

    def end_class(self):
        """
        Exit and return the current context if we are in a class, throw a
        WrongContextError otherwise.
        """
        if self.context.CONTEXT_TYPE == "class":
            return self.exit_context()
        raise WrongContextError("end_class", self.context.CONTEXT_TYPE)

    def begin_method(self, name, arglist=None, returntype=None, kind="method", static=False, override=False):
        """
        Create a new method with the name "name" and parameter list "arglist" and
        return type "returntype".

        The "name" parameter should be a string or an object with a multiname()
        method for converting to an ABC Multiname (QName, TypeName, Multiname,
        Name, etc). A common use is to use a QName with the ns being a private,
        protected or public namespace for access protection.

        "arglist" should be an iterable of (type, name) pairs, with the "name"
        being a string and "type" being an object with a multiname() method for
        specifying the type of the parameter.

        "returntype" should be the same kind of "type" parameter.

        "kind" is the type of method. It can either be "method", "getter", or "setter". If
        it is a getter, it must have a non-void return type and no argument list. If it is
        a setter, it must have a void return type and must take one argument.

        "static" determines whether to add the function to the static or instance
        traits of the class. For a script, this parameter will do nothing.

        "override" has to be set if you attempt to override a method in the
        superclass, including ones from the native Flash Player API.

        To make the constructor method of a class, please use "begin_constructor".
        """
        if self.context.CONTEXT_TYPE not in ("class", "script"):
            raise WrongContextError("begin_method", self.context.CONTEXT_TYPE)
        return self.context.new_method(name, arglist, returntype, kind, static, override)

    def begin_constructor(self, arglist=None):
        """
        Create the constructor method of the current class with the parameter list
        "arglist", also called the "instance initializer".

        "arglist" should be an iterable of (name, type) pairs, with the "name"
        being a string and "type" being an object with a multiname() method for
        specifying the type of the parameter.
        """
        if self.context.CONTEXT_TYPE != "class":
            raise WrongContextError("begin_method", self.context.CONTEXT_TYPE)
        return self.context.make_iinit(arglist)

    def end_method(self):
        """
        Exit and return the current context if we are in a class, throw a
        WrongContextError otherwise.

        This method will work for constructors, but it is is recommended
        you use the "end_constructor" method instead as it does some additional
        checking.
        """
        if self.context.CONTEXT_TYPE == "method":
            return self.exit_context()
        raise WrongContextError("end_method", self.context.CONTEXT_TYPE)

    def end_constructor(self):
        """
        Exit and return the current context if we are in a class, throw a
        WrongContextError otherwise.
        """
        if self.context.CONTEXT_TYPE == "method" and self.context.constructor:
            return self.exit_context()
        raise WrongContextError("end_constructor", self.context.CONTEXT_TYPE)
    
    def finish(self):
        """
        Finalize this generator, by exiting all contexts.

        If you don't finalize before serializing, some code may be missing
        from the final result.
        """
        while self.context:
            self.exit_context()

    def enter_context(self, ctx):
        """
        Enter the context "ctx".
        """
        self.context = ctx

    def exit_context(self):
        """
        Exit the current context and pop the context stack.
        """
        ctx = self.context
        self.context = ctx.exit()
        return ctx

    def exit_until_type(self, TYPE):
        """
        Keep exiting the current context until the current context is of a
        certain type.

        "TYPE" can either be a string, in which case it is one of "global",
        "script", "class", "method", or the actual context type (i.e. ScriptContext).
        """
        while self.context.CONTEXT_TYPE != TYPE or isinstance(TYPE, type) and isinstance(self.context, TYPE):
            self.exit_context()

    def exit_until(self, context):
        """
        Keep exiting the current context until the exact context "context"
        is the current context.

        "context" is compared with an identity/reference equality, so it
        must be the exact one.
        """
        while self.context is not context:
            self.exit_context()

    def current_class(self):
        """
        If we are in a class, return the current class context.

        Otherwise, return None.
        """
        context = self.context
        while context is not None:
            if context.CONTEXT_TYPE == "class":
                return context
            context = context.parent
        return None

    def pop(self):
        """
        Pop an item from the stack.
        """
        self.I(instructions.pop())

    def dup(self):
        """
        Duplicate the top item on the stack.

        In Tamarin, this just duplicates the pointer, it doesn't duplicate the
        actual object.
        """
        self.I(instructions.dup())

    def swap(self):
        """
        Swap the top two items on the stack.
        """
        self.I(instructions.swap())

    def emit(self, instr, *args, **kwargs):
        """
        Emit an instruction, with given arguments.

        The list of possible instruction names is at on the bottom of
        instructions.py
        """
        self.I(instructions.INSTRUCTIONS[instr](*args, **kwargs))

    def set_label(self, lblname):
        """
        Set the current label to be "lblname". The branching machinery
        should be taken care of for you.
        """
        self.emit('label', lblname)

    def branch_unconditionally(self, lblname):
        """
        Branch unconditionally to "lblname", also called a "jump".

        Note: if a jump results a net zero offset, an instruction won't
        be generated.
        """
        self.emit('jump', lblname)

    def branch_conditionally(self, iftrue, lblname):
        """
        Branch to "lblname" if the top of the stack, converted to a
        boolean, is the same as "iftrue", converted to a boolean.
        """
        if iftrue:
            self.branch_if_true(lblname)
        else:
            self.branch_if_false(lblname)

    def branch_if_true(self, lblname):
        self.emit('iftrue', lblname)

    def branch_if_false(self, lblname):
        self.emit('iffalse', lblname)

    def branch_if_equal(self, lblname):
        self.emit('ifeq', lblname)

    def branch_if_strict_equal(self, lblname):
        self.emit('ifstricteq', lblname)

    def branch_if_not_equal(self, lblname):
        self.emit('ifne', lblname)

    def branch_if_strict_not_equal(self, lblname):
        self.emit('ifstrictne', lblname)

    def branch_if_greater_than(self, lblname):
        self.emit('ifgt', lblname)

    def branch_if_greater_equals(self, lblname):
        self.emit('ifge', lblname)

    def branch_if_less_than(self, lblname):
        self.emit('iflt', lblname)

    def branch_if_less_equals(self, lblname):
        self.emit('ifle', lblname)

    def branch_if_not_greater_than(self, lblname):
        self.emit('ifngt', lblname)

    def branch_if_not_greater_equals(self, lblname):
        self.emit('ifnge', lblname)

    def branch_if_not_less_than(self, lblname):
        self.emit('ifnlt', lblname)

    def branch_if_not_less_equals(self, lblname):
        self.emit('ifnle', lblname)

    def call_function_constargs(self, name, *args):
        """
        Call the global function "name" with constant arguments.
        """
        self.emit('findpropstrict', constants.QName(name))
        if args:
            self.load(*args)
        self.emit('callproperty', constants.QName(name), len(args))

    def return_value(self):
        """
        Return a value.
        """
        self.I(instructions.returnvalue())

    def store_var(self, name):
        """
        Stores a local variable.
        
        Pop a value off the stack and store it in the local
        occupied to "name"
        """
        self.SL(name)

    def load(self, v, *args):
        """
        Load arguments onto the stack.

        If an argument has a multiname method, a "getlex" is done
        on the result of calling the multiname.
        """
        if getattr(v, "multiname", None):
            self.I(instructions.getlex(v.multiname()))
        elif isinstance(v, list):
            self.init_array(v)
        elif isinstance(v, dict):
            self.init_object(v)
        else:
            self.push_const(v)

        for i in args:
            self.load(i)

    def push_this(self):
        """
        Push the "this" object onto the stack. In all known cases, this will
        be the local of index 0.
        """
        self.GL("this")

    def push_var(self, v):
        """
        Loads a local variable.
        """
        self.GL(v)

    def push_const(self, v):
        """
        Push the constant "v" onto the stack.

        This will attempt to from python's type system
        to the constant pool types in ABC.

        supported:
          integer and long values      - uses uint and int (and sometimes double) pools
          float values                 - uses the double pool
          basestring (str and unicode) - uses the utf8 pool
          bool                         - uses the pushtrue/pushfalse instructions
        """
        if isinstance(v, (long, int)):
            if v > util.U32_MAX or v < -util.S32_MAX:
                self.I(instructions.pushdouble(
                        self.constants.double_pool.index_for(v)))
                #if v > 0:
                #    self.I(instructions.convert_u())
                #else:
                #    self.I(instructions.convert_i())
            elif 0 <= v < 256:
                self.I(instructions.pushbyte(v))
            elif v >= 0:
                self.I(instructions.pushuint(
                        self.constants.uint_pool.index_for(v)))
            else:
                self.I(instructions.pushint(
                        self.constants.int_pool.index_for(v)))
        elif isinstance(v, basestring):
            self.I(instructions.pushstring(
                    self.constants.utf8_pool.index_for(v)))
        elif isinstance(v, float):
            self.I(instructions.pushdouble(
                    self.constants.double_pool.index_for(v)))
        elif v is True:
            self.I(instructions.pushtrue())
        elif v is False:
            self.I(instructions.pushfalse())
        else:
            assert False, "value for push_const not a literal value"

    def push_undefined(self):
        """
        Load the "undefined" value.
        """
        self.I(instructions.pushundefined())

    def push_null(self):
        """
        Load the "null" value.
        """
        self.I(instructions.pushnull())

    def init_array(self, members=None):
        """
        Initialize an Array with the list "members".
        """
        if members:
            self.load(*members)
        self.I(instructions.newarray(len(members)))

    def init_object(self, members=None):
        """
        Initialize an Object with the dictionary "members".
        """
        if members:
            self.load(*chain(*members.iteritems()))
        self.I(instructions.newobject(len(members)))

    def init_vector(self, TYPE, members=None):
        if members:
            self.load(*members)
        typename = self._get_vector_type(TYPE)
        self.I(instructions.construct(len(members)))
        self.I(instructions.coerce(typename))

    def _get_vector_type(self, TYPE):
        """
        This internal method does two things:

        1. Pushes a Vector applytype'd with TYPE to the top of the stack
        2. Returns a TypeName of Vector with the given TYPE.
        """
        TYPE = self._get_type(TYPE)
        _vec_qname = constants.packagedQName("__AS3__.vec", "Vector")
        self.load(_vec_qname)
        self.load(TYPE)
        self.I(instructions.applytype(1))
        return constants.TypeName(_vec_qname, TYPE)

    def oonewarray(self, TYPE, length=1):
        """
        Creates a strongly typed Vector of the type "TYPE".
        """
        typename = self._get_vector_type(TYPE)
        self.load(length)
        self.I(instructions.construct(1))
        self.I(instructions.coerce(typename))

    def newarray(self, length=1):
        """
        Creates an Array with the given length.
        """
        self.emit('getglobalscope')
        self.push_const(length)
        self.emit('constructprop', constants.QName("Array"), 1)

    def call_function(self, name, argcount):
        """
        Call a global function with "argcount" arguments.
        
        Pop "argcount" values off the stack, pop the receiver (this object)
        off the stack, and calls the method on the receiver with the
        arguments in first-pushed first-argument order.
        """
        name = constants.QName(name)
        self.emit('findpropstrict', name)
        self.emit('callproperty', name, argcount)

    def call_method(self, name, argcount):
        """
        Call a method on an object on the stack with "argcount" arguments on the stack.
        
        Pop "argcount" values off the stack, pop the receiver (this object)
        off the stack, and calls the method on the receiver with the
        arguments in first-pushed first-argument order.
        """
        self.emit('callproperty', constants.QName(name), argcount)

    def set_field(self, fieldname):
        """
        Sets the field "fieldname" on an object.
        
        Pops "value" from the stack. Pops "obj" from the stack. Sets the
        field named "fieldname" on "obj" with the value "value".
        """
        self.emit('setproperty', constants.QName(fieldname))

    def get_field(self, fieldname):
        """
        Gets the field "fieldname" on an object.
        
        Pops an object from the top of the stack, gets the field "fieldname",
        and pushes it on the stack.
        """
        self.emit('getproperty', constants.QName(fieldname))

    def downcast(self, TYPE):
        """
        Attempts to downcast an object to "TYPE".
        
        Pops an object "obj" from the top of the stack, checks if it
        inherits or implements TYPE. If it does, it pushes "obj" back
        on the top of the stack. Otherwise, it pushes the constant null
        on the top of the stack.
        """
        self.emit('coerce', self._get_type(TYPE))

    def isinstance(self, TYPE):
        """
        Checks if an object is an instance of TYPE.
        
        Pops an object from the top of the stack, checks if it inherits or
        implements TYPE, and pushes that boolean onto the stack.
        """
        self.emit('istype', self._get_type(TYPE))

    def gettype(self):
        """
        Takes the top object on the stack, and replaces it with the
        type (constructor) of that object.
        """
        self.get_field("prototype")
        self.get_field("constructor")

    def begin_try(self):
        """
        Begin a try block.
        """
        self.I(instructions.begintry(self.context))

    def end_try(self):
        """
        End a try block.
        """
        self.I(instructions.endtry(self.context))

    def begin_catch(self, TYPE):
        """
        Begin a catch block, attempting to catch TYPE.
        """
        assert self.context.CONTEXT_TYPE == "method"
        name = TYPE.multiname()
        ctx = CatchContext(self, self.context)
        idx = self.context.add_exception(name)
        self.context.restore_scopes()
        self.enter_context(ctx)
        self.emit('newcatch', idx)
        self.dup()
        self.store_var(ctx.local)
        self.dup()
        self.emit('pushscope')
        self.swap()
        self.emit('setslot', 1)

    def push_exception(self, nest=None):
        """
        If we are in a catch block, attempt to push the exception.
        """
        self.emit('getscopeobject', nest or self.context.scope_nest)
        self.emit('getslot', 1)

    def end_catch(self):
        """
        End a catch block.
        """
        self.emit('popscope')
        self.KL(self.context.local)
        self.exit_context()

    def Class(self, name, super_name=None, bases=None):
        """
        Return a context manager that can be used with the with statement
        that calls begin_class and end_class.

        If you are inheriting a Flash Player class, currently you need to
        specify all of the baseclasses that should be on the scope stack,
        excluding "Object", through a list of objects with a multiname()
        method which returns a appropriate QName (QName implements this itself).
        This restriction should go away soon, hopefully.
        
        The "name" and "super_name" parameters should be an object with a
        multiname() method for converting to an ABC Multiname (QName, TypeName,
        Multiname, Name, etc). A common use is to use a QName with the ns being
        a PackageNamespace for packaging classes as found in AS3 and Java. This
        use case is so common that the constants module has a special function
        for making these types of QNames: packagedQName, as used like:

          packagedQName("flash.display", "Sprite")
        """
        return ContextManager((self.begin_class, (name, super_name, bases)), self.end_class)
    
    def Method(self, name, arglist=None, returntype=None, kind="method", static=False, override=False):
        """
        Return a context manager that can be used with the with statement
        that calls begin_method and end_method.

        The "name" parameter should be a string or an object with a multiname()
        method for converting to an ABC Multiname (QName, TypeName, Multiname,
        Name, etc). A common use is to use a QName with the ns being a private,
        protected or public namespace for access protection.

        "arglist" should be an iterable of (type, name) pairs, with the "name"
        being a string and "type" being an object with a multiname() method for
        specifying the type of the parameter.

        "returntype" should be the same kind of "type" parameter.

        "kind" is the type of method. It can either be "method", "getter", or "setter". If
        it is a getter, it must have a non-void return type and no argument list. If it is
        a setter, it must have a void return type and must take one argument.

        "static" determines whether to add the function to the static or instance
        traits of the class. For a script, this parameter will do nothing.

        "override" has to be set if you attempt to override a method in the
        superclass, including ones from the native Flash Player API.

        To make the constructor method of a class, please use "begin_constructor".
        """
        return ContextManager((self.begin_method, (name, arglist, returntype, kind, static, override)), self.end_method)

    def Constructor(self, arglist=None):
        """
        Return a context manager that can be used with the with statement
        that calls begin_method and end_method.

        "arglist" should be an iterable of (name, type) pairs, with the "name"
        being a string and "type" being an object with a multiname() method for
        specifying the type of the parameter.
        """
        return ContextManager((self.begin_constructor, (arglist,)), self.end_constructor)

class ContextManager(object):
    def __init__(self, enter, exit):
        self.enter = enter
        self.exit = exit

    def __enter__(self):
        fn, args = self.enter
        fn(*args)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit()
