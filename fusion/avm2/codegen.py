
from fusion.avm2 import constants, abc_ as abc
from fusion.avm2 import traits, loadable, assembler
from fusion.avm2.interfaces import ILoadable, IMultiname, INode

class Method(object):
    def __init__(self, name, params, rettype,
                 trait_type=traits.MethodTrait,
                 static=False, override=False, prologue=True):
        self.name = IMultiname(name)
        self.param_types, self.param_names = zip(*params) or ([], [])
        self.rettype = rettype
        self.static, self.override = static, override
        self.exceptions = []

        self.asm = assembler.CodeAssembler(['this'] + list(self.param_names))
        if prologue:
            self.asm.emit('getlocal0')
            self.asm.emit('pushscope')

        self.method_info = abc.MethodInfo(str(name), self.param_types, rettype,
                                          param_names=self.param_names)
        self.method_body = abc.MethodBodyInfo(self.method_info, self.asm,
                                              exceptions=self.exceptions)

        self.trait = traits.MethodTrait(self.name, self.method_info,
                                        override=self.override)

class ClassTracker(object):
    def __init__(self):
        self.tracking = {}
        self.order = []

    def track(self, name, rib, bases):
        self.tracking[name] = rib, bases
        self.order.append(name)

    def initialize_classes(self):
        asm = assembler.CodeAssembler([])
        clstraits = []

        for name in self.order:
            rib, bases = self.tracking[name]

            if constants.QName("Object") not in bases:
                bases.append(constants.QName("Object"))

            asm.emit('getscopeobject', 0)

            for base in reversed(bases):
                asm.emit('getlex', base)
                asm.emit('pushscope')

            asm.emit('getlex', rib.super_name)
            asm.emit('newclass', rib.index)
            asm.emit('initproperty', rib.name)

            clstraits.append(traits.ClassTrait(name, rib.classobj))

            for base in bases:
                asm.emit('popscope')

        return asm, clstraits

class ScriptRib(object):
    def __init__(self):
        self.init = None
        self.traits = []
        self.methods = []
        self.tracker = ClassTracker()
        self.done = False

    def make_init(self):
        """
        Create a script init method and enter the context
        for generating code on that method.
        """
        if not self.init:
            self.init = Method("", [], constants.undefined, prologue=False)

        return MethodRib(self.init)

    def new_class(self, name, supercls=None):
        rib = ClassRib(name, supercls)
        self.tracker.track(name, rib, [IMultiname(supercls)]) # XXX
        return rib

    def new_method(self, name, params, rettype, static=False, override=False):
        method = Method(name, params, rettype)
        self.add_trait(method.trait)
        return MethodRib(method)

    def add_trait(self, trait):
        """
        Add a trait to this script, usually used for adding classes,
        script-level variables (slots), and methods.
        """
        self.traits.append(trait)

    def finalize(self, codegen):
        if self.done:
            return

        self.done = True
        if not self.init:
            self.make_init()

        # Make ourselves a new init with the standard prologue,
        # class init sequence and any instructions from the user.
        old_init = self.init.asm.instructions
        self.init.asm.instructions = []

        # Standard prologue.
        self.init.asm.emit('getlocal0')
        self.init.asm.emit('pushscope')

        # Add the class init instructions.
        asm, traits = self.tracker.initialize_classes()
        self.init.asm.instructions += asm.instructions

        self.traits += traits
        self.init.asm.instructions += old_init

        codegen.abc.scripts.index_for(abc.ScriptInfo(self.init.method_info, self.traits))

class ClassRib(object):
    def __init__(self, name, super_name):
        self.name = name
        self.super_name = super_name or "Object"

        self.instance_traits = []
        self.static_traits   = []

        self.cinit = None
        self.iinit = None

    def make_cinit(self, optimize=None):
        if not self.cinit:
            self.cinit = Method("", [], constants.undefined)

        return MethodRib(self.cinit)

    def make_iinit(self, params=None, varargs=None, defaults=None, optimize=None):
        params = params or ()
        if not self.iinit:
            self.iinit = Method("$iinit", params, constants.QName("void"))

            self.iinit.asm.emit('getlocal0')
            self.iinit.asm.emit('constructsuper', 0)

        rib = MethodRib(self.iinit)
        rib.constructor = True
        return rib

    def new_method(self, name, params, rettype, static=False, override=False):
        method = Method(name, params, rettype, static=static, override=override)
        if static:
            self.add_static_trait(method.trait)
        else:
            self.add_instance_trait(method.trait)

        return MethodRib(method)

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

    def finalize(self, codegen):
        if self.iinit is None:
            self.make_iinit()

        if self.cinit is None:
            self.make_cinit()

        self.instance = abc.InstanceInfo(self.name, self.iinit.method_info,
            traits=self.instance_traits, super_name=self.super_name)
        self.classobj = abc.ClassInfo(self.cinit.method_info, traits=self.static_traits)

        self.index = codegen.abc.instances.index_for(self.instance)
        codegen.abc.classes.index_for(self.classobj)

class MethodRib(object):
    scope_nest   = 0
    constructor  = False

    def __init__(self, method):
        self.method = method

    def add_exception(self, param_type):
        """
        This is an internal method made to add Exceptions to a method.

        It uses -1 for from, to, and target values, which should be filled
        in by the bogus addexcinfo, begintry, and endtry "instructions".
        """
        exc = abc.Exception(-1, -1, -1, param_type, "")
        self.method.asm.emit('addexcinfo', self, exc)
        self.method.exceptions.append(exc)
        return len(self.method.exceptions)-1

    def restore_scopes(self):
        """
        Restore the scope stack.
        """
        self.method.asm.emit('getlocal', self.scope_nest)
        self.method.asm.emit('pushscope')

    def finalize(self, codegen):
        codegen.abc.methods.index_for(self.method.method_info)
        codegen.abc.bodies.index_for(self.method.method_body)

class CatchRib(object):
    def __init__(self, parent):
        self.parent = parent
        self.scope_nest = parent.scope_nest + 1
        self.local = "MF::ExceptionLocal%d" % (self.scope_nest,)

    @property
    def method(self):
        return self.parent.method

    def add_exception(self, param_type):
        return self.parent.add_exception(param_type)

    def restore_scopes(self):
        self.parent.restore_scores()
        self.parent.method.asm.load(loadable.Local(self.local))
        self.parent.method.asm.emit("pushscope")

    def finalize(self, codegen):
        pass

class CodeGenerator(object):
    """
    CodeGenerator is a nice generator interface for generating
    common idioms in methods.
    """
    def __init__(self, abc, optimize=False):
        self.abc = abc
        self.constants = self.abc.constants
        self.optimize = optimize

        # Stack of old ribs.
        self.ribs = []
        # Current rib, not on rib stack.
        self.current_rib = None

        self.pending_nodes = []
        self.current_node = None

    def enter_rib(self, rib):
        self.ribs.append(self.current_rib)
        self.current_rib = rib
        return rib

    def exit_current_rib(self):
        self.current_rib.finalize(self)
        self.current_rib = self.ribs.pop()

    def get_current_assembler(self):
        return self.current_rib.method.asm
    current_assembler = property(get_current_assembler)

    def begin_class(self, name, base="Object"):
        """
        Create a new class with the name `name` and superclass `base`.
        """
        return self.enter_rib(self.current_rib.new_class(name, base))

    def begin_method(self, name, params, rettype, static=False, override=False):
        return self.enter_rib(self.current_rib.new_method(name, params, rettype, static, override))

    def begin_script(self):
        return self.enter_rib(ScriptRib())

    def render_nodes(self):
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

    def finish(self):
        """
        Finalize this generator, by rendering all nodes and exiting all
        contexts.

        If you don't finalize before serializing, some code may be missing
        from the final result.
        """

        while self.current_rib:
            self.exit_current_rib()
        self.render_nodes()

    def emit(self, name, *a, **kw):
        """
        Emit an instruction, with given arguments.
        """
        self.current_rib.method.asm.emit(name, *a, **kw)

    def pop(self):
        """
        Pop an item from the stack.
        """
        self.emit('pop')

    def dup(self, TYPE=None):
        """
        Duplicate the top item on the stack.

        In Tamarin, this just duplicates the pointer, it doesn't duplicate the
        actual object.
        """
        self.emit('dup')
        if TYPE:
            self.downcast(TYPE)

    def throw(self):
        """
        Throw the top item on the stack.
        """
        self.emit('throw')

    def swap(self):
        """
        Swap the top two items on the stack.
        """
        self.emit('swap')

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

    def call_function(self, name, args, TYPE=None, void=False):
        """
        Call the global function "name" with the constant arguments "args".

        Find the owner of the function "name", push every element of "args"
        onto the stack, and call the function.

        If a keyword argument "void" that is passed in is True, it will
        use callpropvoid instead of callproperty, which discards the undefined
        return value that exists on the stack.
        """
        self.emit('findpropstrict', name)
        self.call_method(name, None, args, TYPE, void)

    def call_method(self, name, receiver, args=(), TYPE=None, void=False):
        """
        Call the method "name" on "receiver" with args.

        If "TYPE" is passed in, it will attempt to cast the value on the top of the
        stack before returning the value.

        If "void" is True, no object will be on the stack after.
        """

        if receiver:
            self.load(receiver)

        self.load_many(args)

        if void:
            instruction = 'callpropvoid'
        else:
            instruction = 'callproperty'

        self.emit(instruction, name, len(args))

        if TYPE:
            self.downcast(TYPE)

    def construct_type(self, name, args=()):
        self.emit('findpropstrict', name)
        self.load_many(args)
        self.emit('constructprop', name, len(args))

    def return_value(self):
        """
        Return the top value on the stack.
        """
        self.emit('returnvalue')

    def return_void(self):
        """
        Return nothing.
        """
        self.emit('returnvoid')

    def store_var(self, name):
        """
        Stores a local variable.

        Pop a value off the stack and store it in the local
        occupied to "name"

        :param name: the name the local variable
        """
        index = self.current_rib.method.asm.set_local(name)
        self.emit('setlocal', index)
        return index

    def load(self, value):
        """
        Load an ILoadable on to the stack.
        """
        ILoadable(value).load(self)

    def load_many(self, values):
        """
        Load multiple ILoadables on to the stack.
        """
        for value in values:
            self.load(value)

    def init_array(self, members=None):
        """
        Initialize an Array with the list "members".
        """
        if members:
            self.load_many(members)
        self.emit('newarray', len(members))

    def new_array(self, length=1):
        """
        Creates an Array with the given length.
        """
        self.emit('findpropstrict', "Array")
        self.load(length)
        self.emit('constructprop', "Array", 1)

    def init_object(self, members=None):
        """
        Initialize an Object with the dictionary "members".
        """
        for key, val in members.iteritems():
            self.load(key)
            self.load(val)

        self.emit('newobject', len(members))

    def _get_vector_type(self, TYPE):
        """
        Returns a TypeName of Vector with the given TYPE.
        """
        from fusion.avm2 import playerglobal
        TYPE = IMultiname(TYPE)
        Vector = playerglobal.__AS3__.vec.Vector
        if TYPE in Vector.SpecializedFast:
            return Vector.SpecializedFast[TYPE]
        return constants.TypeName(Vector, (TYPE,))

    def init_vector(self, TYPE, members=None):
        """
        Initializes a Vector of TYPE with the list "members".
        """
        typename = self._get_vector_type(TYPE)
        self.load(typename)
        self.load_many(members)
        self.emit('construct', len(members))
        self.downcast(typename)

    def new_vector(self, TYPE, length=1):
        """
        Creates a strongly typed Vector of the type "TYPE".
        """
        typename = self._get_vector_type(TYPE)
        self.load(typename)
        self.load(length)
        self.emit('construct', 1)
        self.downcast(typename)

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
        self.emit('setproperty', fieldname)

    fast_cast = {
        constants.QName("String"):  'coerce_s',
        constants.QName("*"):       'coerce_a',
        constants.QName("uint"):    'convert_u',
        constants.QName("int"):     'convert_i',
        constants.QName("Number"):  'convert_d',
        constants.QName("Object"):  'convert_o',
        constants.QName("Boolean"): 'convert_b',
    }

    def downcast(self, TYPE):
        """
        Attempts to downcast an object to "TYPE".

        Pops an object "obj" from the top of the stack, checks if it
        inherits or implements TYPE. If it does, it pushes "obj" back
        on the top of the stack. Otherwise, it pushes the constant null
        on the top of the stack.
        """
        TYPE = IMultiname(TYPE)
        if TYPE in self.fast_cast:
            self.emit(self.fast_cast[TYPE])
        else:
            self.emit('coerce', TYPE)

    def isinstance(self, TYPE):
        """
        Checks if an object is an instance of TYPE.

        Pops an object from the top of the stack, checks if it inherits or
        implements TYPE, and pushes that boolean onto the stack.
        """
        self.emit('istype', IMultiname(TYPE))

    def gettype(self):
        """
        Takes the top object on the stack, and replaces it with the
        type (constructor) of that object.
        """
        self.load(loadable.Field("constructor"))

    def begin_try(self):
        """
        Begin a try block.
        """
        self.emit('begintry', self.current_rib)

    def end_try(self):
        """
        End a try block.
        """
        self.emit('endtry', self.current_rib)

    def begin_catch(self, TYPE):
        """
        Begin a catch block, attempting to catch TYPE.
        """
        name = IMultiname(TYPE)
        rib = CatchRib(self.current_rib)
        idx = self.current_rib.add_exception(name)
        self.current_rib.restore_scopes()
        self.enter_rib(rib)
        self.emit('begincatch')
        self.emit('newcatch', idx)
        self.dup()
        self.store_var(rib.local)
        self.dup()
        self.emit('pushscope')
        self.swap()
        self.emit('setslot', 1)

    def push_exception(self, nest=None):
        """
        Attempt to push the current exception.
        """
        self.emit('getscopeobject', nest or self.current_rib.scope_nest)
        self.load(loadable.Slot(1))

    def end_catch(self):
        """
        End a catch block.
        """
        self.emit('popscope')
        self.emit('kill', self.current_rib.method.asm.kill_local(self.current_rib.local))
        self.exit_current_rib()

    def add_node(self, node):
        """
        Add a node to the pending nodes of this code generator.
        """
        self.pending_nodes.append(INode(node))
