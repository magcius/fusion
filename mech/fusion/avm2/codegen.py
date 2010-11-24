
from mech.fusion.compat import set

from mech.fusion.avm2 import constants, instructions, abc_ as abc
from mech.fusion.avm2 import library, traits, util, playerglobal
from mech.fusion.avm2.interfaces import ILoadable, LoadableAdapter
from mech.fusion.avm2.interfaces import IMultiname, INode
from mech.fusion.avm2.assembler import CodeAssembler

from zope.interface import implements
from zope.component import adapter, provideAdapter

from copy import copy
from math import isnan
from itertools import chain

NAME_PARAMETER = """
:param name: should be a string or an object%s adaptable to an IMultiname,
             the interface for representing ABC Multinames (QName,
             TypeName, Multiname, etc). A common use is to use a
             QName with the ns being a private, protected or public
             namespace for access protection.
""".strip()

PARAMS_PARAMETER = """
:param params: should be an iterable of (type, name) pairs, with the
               "name"  being a string and "type" being an object with a
               multiname() method for specifying the type of the parameter.
""".strip()

VARDEF_PARAMETER = """
:param varargs: The name of the "...rest" or \*args argument.

:param defaults: The values for the default parameters.
""".strip()

OPTIMIZE_PARAMETER = """
:param optimize: Determines whether the code should undergo simple
                optimizations. It may be useful to turn this off
                for debugging.
""".strip()

METHOD_CREATOR = """
Create a new method with the name "name" and parameter list "arglist"
and return type "returntype".

%s

%s

:param returntype: should be the same kind of "type" parameter
                   describing the return type of the method.

:param kind: The kind of method. It can either be "method", "getter", or
             "setter". If it is a getter, it must have a non-void return type
             and no argument list. If it is a setter, it must have a
             void return type and must take one argument.

:param static: Determines whether to add the function to the static or
               instance traits of the class. For a script, this parameter
               will do nothing.

:param override: marks the the method as overridden, which is required for
                 Tamarin, even for native Flash Player classes. In most cases
                 this should be set automatically.

%s

%s

:return: The MethodContext object created.
""" % (NAME_PARAMETER % (" describing the name of the method",),
PARAMS_PARAMETER,
VARDEF_PARAMETER,
OPTIMIZE_PARAMETER,)

class WrongContextError(BaseException):
    def __init__(self, method, current):
        self.method, self.current = method, current

    def __str__(self):
        return ("You called %r while the current context was"
                " a %s context." % (self.method, self.current))

class GlobalContext(object):
    """
    A global context that can only create scripts.
    """
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
    def new_method_info(self, name, params, rettype, varargs, defaults):
        """
        An internal function for generating an AbcMethodInfo
        with the given name, parameters, and return type, "...rest"
        variable names and default values.
        """
        return abc.AbcMethodInfo(name, [self.gen._get_type(t) for t, n in params],
               self.gen._get_type(rettype), param_names=[n for t, n in params],
               varargs=varargs, options=defaults)

    def new_method(self, name, params=None, rettype=None, kind="method",
                   static=False, override=False, varargs=None, defaults=None,
                   optimize=None):
        params = params or []
        name = self.gen._get_type(name)
        meth = self.new_method_info(str(name), params,
                    rettype or constants.QName("void"), varargs, defaults)

        KIND = dict(method=traits.AbcMethodTrait, getter=traits.AbcGetterTrait,
                    setter=traits.AbcSetterTrait)

        trait = KIND.get(kind, traits.AbcMethodTrait)(name, meth,
                         override=override or self.overridden(static, name))

        ctx = MethodContext(self.gen, meth, self, params,
                            optimize=optimize or self.gen.optimize)
        ctx.trait = trait
        return ctx

    new_method.__doc__ = METHOD_CREATOR

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

    def overridden(self, static, name):
        """
        Determines whether a method name "name" should be
        marked with the "override" flag.

        :param static: Whether the method is static.
        :param name: The name of the method.

        :return: Whether the method should be marked with
                 the override flag.
        """
        return False

    def make_init(self, optimize=None):
        """
        Create a script init method and enter the context
        for generating code on that method.
        """
        if not self.init:
            self.init = abc.AbcMethodInfo("", [], constants.undefined)
            self.init.ctx = MethodContext(self.gen, self.init, self, [],
                                          optimize=optimize or self.gen.optimize)
        self.gen.enter_context(self.init.ctx)
        return self.init.ctx

    def new_class(self, name, super_name=None, bases=None):
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

    new_class.__doc__ = """
    Create a new class and enter the context for that class.

    This will generate both the AbcInstance and the AbcClass.

    %s

    :param super_name: The same type of object describing the base type of the
                       class. If left blank or None is provided the class will
                       extend "Object".

    :param bases: A list of base classes that need to be on the scope stack. If
                  this is a stdlib class, this shouldn't need to be provided.
    """ % (NAME_PARAMETER % (" describing the name of the class",),)

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

        # Save all instructions after the scope.
        insts = []
        if meth.asm.instructions[2:]:
            insts = meth.asm.instructions[2:]
            meth.asm.instructions = meth.asm.instructions[:2]

        for key in self.pending_classes_order:
            context, parents = self.pending_classes[key]
            if parents is None:
                parents = []
                ctx = self.gen.get_class_context(context.super_name, self.pending_classes)
                while ctx:
                    parents.append(ctx.name)
                    ctx = self.gen.get_class_context(ctx.super_name, self.pending_classes)

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

        self.gen.abc.scripts.index_for(abc.AbcScriptInfo(self.init, self.traits))
        self.gen.exit_context()

        # And add them after the class init.
        meth.asm.instructions += insts
        return self.parent

class ClassContext(_MethodContextMixin):
    CONTEXT_TYPE = "class"

    def __init__(self, gen, name, super_name, parent):
        self.gen = gen
        self.name = name
        self.super_name = super_name or "Object"
        self.parent = parent
        self.instance_traits = []
        self.static_traits   = []
        self.cinit = None
        self.iinit = None

    def overridden(self, static, name):
        """
        Determines whether a method name "name" should be mared with the
        "override" flag.

        :param static: Whether the method is static.
        :param name: The name of the method.

        :return: Whether the method should be marked with
                the override flag.
        """
        ctx = self.gen.get_class_context(self.name)
        while ctx:
            if static and IMultiname(name) in ctx.StaticMethods:
                return True
            elif not static and IMultiname(name) in ctx.Methods:
                return True
            ctx = self.gen.get_class_context(ctx.super_name)
        return False

    def make_cinit(self, optimize=None):
        if not self.cinit:
            self.cinit = abc.AbcMethodInfo("", [], constants.undefined)
            self.cinit.ctx = MethodContext(self.gen, self.cinit, self, [],
                                   optimize=optimize or self.gen.optimize)
        self.gen.enter_context(self.cinit.ctx)
        return self.cinit.ctx

    make_cinit.__doc__ = """
    Create a cinit (class initializer) method used to set up static
    traits and variables, and enter the correct context to generate
    code on it.

    cinits are usually called when the first instance of a class is
    created, although it is sometimes called when the "newclass" opcode
    is run.

    %s

    :return: The MethodContext object created.
    """ % (OPTIMIZE_PARAMETER,)

    def make_iinit(self, params=None, varargs=None, defaults=None, optimize=None):
        params = params or ()
        if self.iinit:
            if params:
                raise ValueError("parameters cannot be redefined")
        else:
            self.iinit = self.new_method_info("", params, constants.QName("void"),
                                              varargs=varargs, defaults=defaults)
            self.iinit.ctx = MethodContext(self.gen, self.iinit, self, [],
                                   optimize=optimize or self.gen.optimize)
            self.iinit.ctx.constructor = True

        self.gen.enter_context(self.iinit.ctx)

        if not self.iinit.done:
            self.gen.push_this()
            self.gen.emit("constructsuper", 0)

    make_iinit.__doc__ = """
    Create a iinit (instance initializer) method used to set up instance
    variables, and enter the correct context to generate code on it.

    iinits are always called when an instance of a class is created using
    the "new" operator in ECMAScript, which translates into the
    "constructprop" opcode in ABC.

    %s

    %s

    %s

    :return: The MethodContext object created.
    """ % (PARAMS_PARAMETER, VARDEF_PARAMETER, OPTIMIZE_PARAMETER)

    def add_instance_trait(self, trait):
        """
        Add an instance-level trait. Traits are not only used for
        instance variables (slots) but also used for method declarations.
        """
        self.instance_traits.append(trait)

    def add_static_trait(self, trait):
        """
        Add a static-level trait. Traits are not only used for
        instance variables (slots) but also used for method declarations.
        """
        self.static_traits.append(trait)

    def exit(self):
        assert self.parent.CONTEXT_TYPE == "script"
        if self.iinit is None:
            self.make_iinit()
            self.gen.end_constructor()
        if self.cinit is None:
            self.make_cinit()
            self.gen.end_method()
        self.instance = abc.AbcInstanceInfo(self.name, self.iinit,
            traits=self.instance_traits, super_name=self.super_name)
        self.classobj = abc.AbcClassInfo(self.cinit, traits=self.static_traits)
        self.index = self.gen.abc.instances.index_for(self.instance)
        self.gen.abc.classes.index_for(self.classobj)
        return self.parent

class MethodContext(_MethodContextMixin):
    CONTEXT_TYPE = "method"
    scope_nest   = 0
    constructor  = False

    def __init__(self, gen, method, parent, params,
                 stdprologue=True, optimize=None):
        self.gen, self.method = gen, method
        self.parent, self.optimize = parent, optimize
        self.params = params
        if params:
            self.param_types, self.param_names = map(list, zip(*params))
        else:
            self.param_types, self.param_names = [], []
        self.asm = CodeAssembler(gen.constants, ['this']+self.param_names)
        self.label_counters = {}
        self.acv_traits = []
        self.exceptions = []
        self.body = abc.AbcMethodBodyInfo(self.method, self.asm,
                    self.acv_traits, self.exceptions, self.optimize)
        if stdprologue:
            self.restore_scopes()

    def exit(self):
        self.gen.abc.methods.index_for(self.method)
        self.gen.abc.bodies.index_for(self.body)
        return self.parent

    def next_label(self, prefix='label'):
        current = self.label_counters.get(prefix, 0)
        self.label_counters[prefix] = current+1
        return "__%s_%d" % (prefix, current)

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
        Return the next free local variable (register).
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
        the freed local. This does not produce a "kill" opcode,
        please use the generator interface for this.
        """
        return self.asm.kill_local(name)

    def get_local(self, name):
        """
        Get the index for the local/register identified with "name".
        This does not produce a "getlocal" opcode, please use the
        generator interface for this.
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

@adapter(list)
class ListLoadable(LoadableAdapter):
    def load(self, generator):
        generator.init_array(self.value)

provideAdapter(ListLoadable)

@adapter(dict)
class DictLoadable(LoadableAdapter):
    def load(self, generator):
        generator.init_object(self.value)

provideAdapter(DictLoadable)

@adapter(bool)
class BoolLoadable(LoadableAdapter):
    def load(self, generator):
        if self.value:
            generator.push_true()
        else:
            generator.push_false()

provideAdapter(BoolLoadable)

class IntLoadable(LoadableAdapter):
    def load(self, generator):
        v = self.value
        if v > util.U32_MAX or v < -util.S32_MAX:
            generator.I(instructions.pushdouble(v))
        elif v >= 0:
            generator.I(instructions.pushuint(v))
        else:
            generator.I(instructions.pushint(v))

provideAdapter(IntLoadable, [int], ILoadable)
provideAdapter(IntLoadable, [long], ILoadable)

@adapter(float)
class FloatLoadable(LoadableAdapter):
    def load(self, generator):
        v = self.value
        if isnan(v):
            generator.I(instructions.pushnan())
        else:
            generator.I(instructions.pushdouble(v))

provideAdapter(FloatLoadable)

@adapter(basestring)
class BaseStringLoadable(LoadableAdapter):
    def load(self, generator):
        generator.I(instructions.pushstring(self.value))

provideAdapter(BaseStringLoadable)

class NotAnArgumentError(Exception):
    def __init__(self, name):
        self.name = name

    def __str__(self):
        return ("The local variable %r is not an argument"
                "in the current method.") % (self.name,)

class Local(object):
    implements(ILoadable)
    """
    A loadable object that pushes a local onto the stack.
    """
    def __init__(self, name):
        self.name = name

    def load(self, generator):
        generator.push_var(self.name)

    def __repr__(self):
        return "Local(%r)" % (self.name,)

class Argument(object):
    implements(ILoadable)
    """
    A loadable object that pushes a method argument onto the stack.
    """
    def __init__(self, name):
        self.name = name

    def load(self, generator):
        generator.push_arg(self.name)

    def __repr__(self):
        return "Argument(%r)" % (self.name,)

class CodeGenerator(object):

    Argument = Argument
    Local = Local
    
    """
    CodeGenerator is a nice generator interface for generating
    common idioms in methods.
    """
    def __init__(self, abc_=None, make_script=True, optimize=True):
        self.abc = abc_ or abc.AbcFile()
        self.constants = self.abc.constants
        self.context = GlobalContext(self)
        self.optimize = optimize
        self.current_node = None

        self.pending_nodes = []

        if make_script:
            self.script0 = self.context.new_script()

    def _get_type(self, TYPE):
        """
        An internal function designed to get a QName for
        a special construct of a "TYPE"
        """
        return IMultiname(TYPE)

    def get_class_context(self, name, DICT={}):
        """
        An internal function designed to get a certain
        class context for a name and a fallback dict

        This method uses the native library API to find
        a native playerglobal class.
        """
        if library.type_exists(name):
            TYPE = copy(library.get_type(name))
            TYPE.super_name = TYPE.BaseType
            TYPE.name       = TYPE.FullName
            return TYPE
        return DICT.get(name, [None])[0]

    def I(self, *i):
        """
        Add the instructions to the current method.
        """
        self.context.add_instructions(i)

    def SL(self, name):
        """
        Pop a value off the stack and set it in the local
        occupied to "name".

        Stands for "set local"
        """
        index = self.context.set_local(name)
        self.I(instructions.setlocal(index))
        return index

    def GL(self, name):
        """
        Get the local occupied to "name" and push it to the stack.

        Stands for "get local"
        """
        index = self.context.get_local(name)
        self.I(instructions.getlocal(index))
        return index

    def KL(self, name, empty=False):
        """
        Kill the local currently occupied to "name"

        The argument "empty" will set the local as empty and ready for reuse.
        Only set this to True if you are completely sure it is safe.

        Stands for "kill local"
        """
        if empty:
            index = self.context.kill_local
        else:
            index = self.context.get_local
        self.I(instructions.kill(index(name)))

    def HL(self, name):
        """
        Return True if there is a local by the name of "name".

        Stands for "has local"
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
        for making these types of QNames, packagedQName, as used like::

          packagedQName("flash.display", "Sprite")
        """
        return self.context.new_class(name, super_name, bases)

    def end_class(self):
        """
        Exit and return the current context if we are in a class, raise a
        WrongContextError otherwise.
        """
        if self.context.CONTEXT_TYPE == "class":
            return self.exit_context()
        raise WrongContextError("end_class", self.context.CONTEXT_TYPE)

    def begin_method(self, name, arglist=None, returntype=None, kind="method",
                     static=False, override=False, varargs=None, defaults=None,
                     optimize=None):
        if self.context.CONTEXT_TYPE not in ("class", "script"):
            raise WrongContextError("begin_method", self.context.CONTEXT_TYPE)

        ctx = self.context.new_method(name, arglist, returntype, kind, static,
                                      override, varargs, defaults, optimize)
        if static:
            self.context.add_static_trait(ctx.trait)
        else:
            self.context.add_instance_trait(ctx.trait)

        self.enter_context(ctx)

    begin_method.__doc__ = METHOD_CREATOR

    def begin_constructor(self, arglist=None, params=None, varargs=None, defaults=None,
                          optimize=None):
        if self.context.CONTEXT_TYPE != "class":
            raise WrongContextError("begin_constructor",
                                    self.context.CONTEXT_TYPE)
        return self.context.make_iinit(arglist, varargs, defaults, optimize)

    begin_constructor.__doc__ = """
    Create the constructor method of the current class with the parameter
    list "arglist", also called the "instance initializer"

    %s

    %s
    """ % (PARAMS_PARAMETER, OPTIMIZE_PARAMETER)

    def end_method(self):
        """
        Exit and return the current context if we are in a class, raose a
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
        Exit and return the current context if we are in a class, raise a
        WrongContextError otherwise.
        """
        if self.context.CONTEXT_TYPE == "method" and self.context.constructor:
            return self.exit_context()
        raise WrongContextError("end_constructor", self.context.CONTEXT_TYPE)

    def finish(self):
        """
        Finalize this generator, by rendering all nodes and exiting all
        contexts.

        If you don't finalize before serializing, some code may be missing
        from the final result.
        """
        self.exit_until_type("script")
        done = set()
        while self.pending_nodes:
            node = self.pending_nodes.pop()
            for dep in node.dependencies():
                if dep not in done:
                    self.current_node = dep
                    dep.render(self)
                    done.add(dep)
            self.current_node = node
            node.render(self)
            done.add(node)
        self.current_node = None
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
        "script", "class", "method", or the actual context type
        (i.e. ScriptContext).
        """
        while self.context.CONTEXT_TYPE != TYPE or isinstance(TYPE, type) and \
                  isinstance(self.context, TYPE):
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

    def dup(self, TYPE=None):
        """
        Duplicate the top item on the stack.

        In Tamarin, this just duplicates the pointer, it doesn't duplicate the
        actual object.
        """
        self.I(instructions.dup())
        if TYPE:
            self.downcast(TYPE)

    def throw(self):
        """
        Throw the top item on the stack.
        """
        self.I(instructions.throw())

    def swap(self):
        """
        Swap the top two items on the stack.
        """
        self.I(instructions.swap())

    def emit(self, instr, *args, **kwargs):
        """
        Emit an instruction, with given arguments.

        The list of possible instruction names is at the bottom of
        instructions.py
        """
        self.I(instructions.INSTRUCTIONS[instr](*args, **kwargs))

    def next_label(self, prefix='label'):
        return self.context.next_label(prefix)

    def set_label(self, lblname):
        """
        Set the current label to be "lblname". The branching machinery
        should be taken care of for you.
        """
        self.emit('label', lblname)

    def branch_unconditionally(self, lblname):
        """
        Branch unconditionally to "lblname", also called a "jump".

        Note: if a jump results in a net zero offset, a jump instruction
        won't be generated.
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
        self.I(instructions.iftrue(lblname))

    def branch_if_false(self, lblname):
        self.I(instructions.iffalse(lblname))

    def branch_if_equal(self, lblname):
        self.I(instructions.ifeq(lblname))

    def branch_if_strict_equal(self, lblname):
        self.I(instructions.ifstricteq(lblname))

    def branch_if_not_equal(self, lblname):
        self.I(instructions.ifne(lblname))

    def branch_if_strict_not_equal(self, lblname):
        self.I(instructions.ifstrictne(lblname))

    def branch_if_greater_than(self, lblname):
        self.I(instructions.ifgt(lblname))

    def branch_if_greater_equals(self, lblname):
        self.I(instructions.ifge(lblname))

    def branch_if_less_than(self, lblname):
        self.I(instructions.iflt(lblname))

    def branch_if_less_equals(self, lblname):
        self.I(instructions.ifle(lblname))

    def branch_if_not_greater_than(self, lblname):
        self.I(instructions.ifngt(lblname))

    def branch_if_not_greater_equals(self, lblname):
        self.I(instructions.ifnge(lblname))

    def branch_if_not_less_than(self, lblname):
        self.I(instructions.ifnlt(lblname))

    def branch_if_not_less_equals(self, lblname):
        self.I(instructions.ifnle(lblname))

    def call_function_constargs(self, name, *args, **kwargs):
        """
        Call the global function "name" with the constant arguments "args".

        Find the owner of the function "name", push every element of "args"
        onto the stack, and call the function.

        If a keyword argument "void" that is passed in is True, it will
        use callpropvoid instead of callproperty, which discards the undefined
        return value that exists on the stack.
        """
        self.I(instructions.findpropstrict(name))
        self.call_method_constargs(name, None, *args, **kwargs)

    def call_method_constargs(self, name, target, *args, **kwargs):
        """
        Call a method on "target" with the constant arguments
        "args". If a keyword argument "void" that is passed in is True, it will
        use callpropvoid instead of callproperty, which discards the undefined
        return value that exists on the stack.
        """
        if target:
            self.load(target)
        if args:
            self.load(*args)
        self.call_method(name, len(args), kwargs.pop("TYPE", None), kwargs.pop("void", False))

    def call_function(self, name, argcount, TYPE=None, void=False):
        """
        Call a global function with "argcount" arguments.

        Pop "argcount" values off the stack, pop the receiver (this object)
        off the stack, and calls the method on the receiver with the
        arguments in first-pushed first-argument order.
        """
        self.I(instructions.findpropstrict(name))
        self.call_method(name, argcount, TYPE, void)

    def call_method(self, name, argcount, TYPE=None, void=False):
        """
        Call a method on an object on the stack with "argcount" arguments on the stack.

        If "TYPE" is passed in, it will attempt to cast the value on the top of the
        stack before returning the value.

        Pop "argcount" values off the stack, pop the receiver (this object)
        off the stack, and calls the method on the receiver with the
        arguments in first-pushed first-argument order.
        """
        if void:
            i = instructions.callpropvoid
        else:
            i = instructions.callproperty
        self.I(i(IMultiname(name), argcount))
        if TYPE:
            self.downcast(TYPE)

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

        :param name: the name the local variable
        """
        self.SL(name)

    def load(self, *args):
        """
        Load arguments onto the stack.

        If an argument has a multiname method, a "getlex" is done
        on the result of calling the multiname.
        """
        for v in args:
            loadable = None
            try:
                loadable = ILoadable(v)
            except TypeError:
                try:
                    loadable = ILoadable(IMultiname(v))
                except TypeError:
                    raise
            loadable.load(self)

    push_const = load

    def push_this(self):
        """
        Push the "this" object onto the stack. In all known cases, this will
        be the local of index 0. Equivalent to GL("this").
        """
        self.GL("this")

    def push_var(self, name):
        """
        Load the local variable "name".
        """
        self.GL(name)

    def push_arg(self, name):
        """
        Load the local variable "name", which has to also be an argument.
        """
        if not name in self.context.param_names:
            raise NotAnArgumentError(name)
        self.GL(name)

    def push_true(self):
        """
        Load the "true" value.
        """
        self.I(instructions.pushtrue())

    def push_false(self):
        """
        Load the "false" value.
        """
        self.I(instructions.pushfalse())

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

    def new_array(self, length=1):
        """
        Creates an Array with the given length.
        """
        self.I(instructions.getglobalscope())
        self.load(length)
        self.I(instructions.constructprop(constants.QName("Array"), 1))

    def init_object(self, members=None):
        """
        Initialize an Object with the dictionary "members".
        """
        if members:
            self.load(*chain(*members.iteritems()))
        self.I(instructions.newobject(len(members)))

    def _get_vector_type(self, TYPE):
        """
        Returns a TypeName of Vector with the given TYPE.
        """
        from mech.fusion.avm2 import playerglobal
        TYPE = self._get_type(TYPE)
        Vector = playerglobal.__AS3__.vec.Vector
        if TYPE in Vector.SpecializedFast:
            return Vector.SpecializedFast[TYPE]
        return constants.TypeName(Vector, TYPE)

    def init_vector(self, TYPE, members=None):
        """
        Initializes a Vector of TYPE with the list "members".
        """
        typename = self._get_vector_type(TYPE)
        self.load(typename, *members)
        self.I(instructions.construct(len(members)))
        self.I(instructions.coerce(typename))

    def new_vector(self, TYPE, length=1):
        """
        Creates a strongly typed Vector of the type "TYPE".
        """
        typename = self._get_vector_type(TYPE)
        self.load(typename, length)
        self.I(instructions.construct(1))
        self.I(instructions.coerce(typename))

    def set_field(self, fieldname, TYPE=None):
        """
        Sets the field "fieldname" on an object. If "TYPE" is passed in,
        it will attempt to cast the value on the top of the stack before
        setting the field.

        Pops "value" from the stack. Pops "obj" from the stack. Sets the
        field named "fieldname" on "obj" with the value "value".
        """
        if TYPE:
            self.downcast(TYPE)
        self.I(instructions.setproperty(IMultiname(fieldname)))

    def get_field(self, fieldname, TYPE=None):
        """
        Gets the field "fieldname" on an object. If "TYPE" is passed in,
        it will attempt to cast the value on the top of the stack before
        returning the value.

        Pops an object from the top of the stack, gets the field "fieldname",
        and pushes it on the stack.
        """
        self.I(instructions.getproperty(IMultiname(fieldname)))
        if TYPE:
            self.downcast(TYPE)

    fast_cast = {
        constants.QName("String"):  instructions.coerce_s(),
        constants.QName("*"):       instructions.coerce_a(),
        constants.QName("uint"):    instructions.convert_u(),
        constants.QName("int"):     instructions.convert_i(),
        constants.QName("Number"):  instructions.convert_d(),
        constants.QName("Object"):  instructions.convert_o(),
        constants.QName("Boolean"): instructions.convert_b(), }

    def downcast(self, TYPE):
        """
        Attempts to downcast an object to "TYPE".

        Pops an object "obj" from the top of the stack, checks if it
        inherits or implements TYPE. If it does, it pushes "obj" back
        on the top of the stack. Otherwise, it pushes the constant null
        on the top of the stack.
        """
        TYPE = self._get_type(TYPE)
        if TYPE in self.fast_cast:
            self.I(self.fast_cast[TYPE])
        else:
            self.I(instructions.coerce(TYPE))

    def isinstance(self, TYPE):
        """
        Checks if an object is an instance of TYPE.

        Pops an object from the top of the stack, checks if it inherits or
        implements TYPE, and pushes that boolean onto the stack.
        """
        self.I(instructions.istype(self._get_type(TYPE)))

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
        name = IMultiname(TYPE)
        ctx = CatchContext(self, self.context)
        idx = self.context.add_exception(name)
        self.context.restore_scopes()
        self.enter_context(ctx)
        self.I(instructions.begincatch())
        self.I(instructions.newcatch(idx))
        self.dup()
        self.store_var(ctx.local)
        self.dup()
        self.I(instructions.pushscope())
        self.swap()
        self.I(instructions.setslot(1))

    def push_exception(self, nest=None):
        """
        Attempt to push the current exception.
        """
        self.I(instructions.getscopeobject(nest or self.context.scope_nest))
        self.I(instructions.getslot(1))

    def end_catch(self):
        """
        End a catch block.
        """
        self.I(instructions.popscope())
        self.KL(self.context.local)
        self.exit_context()

    def add_node(self, node):
        """
        Add a node to the pending nodes of this code generator.
        """
        self.pending_nodes.append(INode(node))

    def Class(self, name, super_name=None, bases=None):
        return ContextManager((self.begin_class, (name, super_name, bases)),
                              self.end_class)

    Class.__doc__ = """
    Return a context manager that can be used with the with statement
    that calls begin_class and end_class.
    """ + begin_class.__doc__

    def Method(self, name, arglist=None, returntype=None, kind="method",
               static=False, optimize=None, varargs=None, defaults=None):
        return ContextManager((self.begin_method, (name, arglist, returntype,
                              kind, static, optimize, varargs, defaults)),
                              self.end_method)

    Method.__doc__ = """
        Return a context manager that can be used with the with statement
        that calls begin_method and end_method.
    """ + begin_method.__doc__

    def Constructor(self, arglist=None, varargs=None, defaults=None,
                    optimize=None):
        return ContextManager((self.begin_constructor, (arglist, varargs,
                               defaults, optimize)), self.end_constructor)

    Constructor.__doc__ = """
    Return a context manager that can be used with the with statement
    that calls begin_constructor and end_constructor.
    """ + begin_constructor.__doc__


class ContextManager(object):
    def __init__(self, enter, exit):
        self.enter = enter
        self.exit = exit

    def __enter__(self):
        fn, args = self.enter
        return fn(*args)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit()
