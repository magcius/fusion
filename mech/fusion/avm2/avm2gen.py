
from mech.fusion.avm2 import assembler, constants, instructions, \
    abc_ as abc, traits, util

from itertools import chain

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
    def new_method_info(self, name, params, rettype):
        return abc.AbcMethodInfo(name,
                                 [t.multiname() for t, n in params],
                                 rettype.multiname(),
                                 param_names=[n for t, n in params])
    
    def new_method(self, name, params, rettype, static=False, override=False):
        meth = self.new_method_info(name, params, rettype)
        trait = traits.AbcMethodTrait(constants.QName(name), meth, override=override)
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
    
    def make_init(self):
        if not self.init:
            self.init = abc.AbcMethodInfo("", [], constants.ANY_NAME)
        ctx = MethodContext(self.gen, self.init, self, [])
        self.gen.enter_context(ctx)
        return ctx
    
    def new_class(self, name, super_name=None, bases=None):
        # allow hardcoded bases
        ctx = ClassContext(self.gen, name, super_name, self)
        self.pending_classes[name] = (ctx, bases)
        self.pending_classes_order.append(name)
        self.gen.enter_context(ctx)
        return ctx

    def add_trait(self, trait):
        self.traits.append(trait)

    add_static_trait = add_trait
    add_instance_trait = add_trait
    
    def exit(self):
        assert self.parent.CONTEXT_TYPE == "global"

        self.make_init()
        
        for key in self.pending_classes_order:
            context, parents = self.pending_classes[key]

            if parents is None:
                parents = []
                ctx = self.gen.get_class_context(context.super_name, self.pending_classes)
                while ctx:
                    parents.append(ctx.name)
                    ctx = self.gen.get_class_context(ctx.super_name, self.pending_classes)

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
        if not self.cinit:
            self.cinit = abc.AbcMethodInfo("", [], constants.ANY_NAME)
        ctx = MethodContext(self.gen, self.cinit, self, [])
        self.gen.enter_context(ctx)
        return ctx

    def make_iinit(self, params=None):
        params = params or ()
        if self.iinit:
            if params:
                raise ValueError("parameters cannot be redefined")
        else:
            self.iinit = self.new_method_info("", params, constants.QName("void"))

        ctx = MethodContext(self.gen, self.iinit, self, [])
        self.gen.enter_context(ctx)
        
        self.gen.I(instructions.getlocal(0))
        self.gen.I(instructions.constructsuper(0))

    def add_instance_trait(self, trait):
        self.instance_traits.append(trait)
        return len(self.instance_traits)

    def add_static_trait(self, trait):
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
        self.asm.add_instruction(instructions.returnvoid())
        self.gen.abc.methods.index_for(self.method)
        self.gen.abc.bodies.index_for(abc.AbcMethodBodyInfo(
                self.method, self.asm, self.acv_traits, self.exceptions))
        return self.parent

    def add_activation_trait(self, trait):
        self.acv_traits.append(trait)
        return len(self.acv_traits)

    def add_exception(self, param_type, param_name):
        self.exceptions.append(abc.AbcException(self.code_start,
                self.code_end, len(self.asm), param_type, param_name))
        return len(self.exceptions)-1

    def start_catch(self):
        self.asm.scope_depth += 1
    
    def add_instructions(self, *i):
        self.asm.add(*i)
    
    @property
    def next_free_local(self):
        return self.asm.next_free_local

    def set_local(self, name):
        return self.asm.set_local(name)

    def kill_local(self, name):
        return self.asm.kill_local(name)

    def get_local(self, name):
        return self.asm.get_local(name)

    def has_local(self, name):
        return self.asm.has_local(name)

    def restore_scopes(self):
        self.gen.push_this()
        self.gen.emit("pushscope")

class CatchContext(object):
    def __init__(self, gen, parent):
        self.gen = gen
        self.parent = parent

    def __getattr__(self, name):
        return getattr(self.parent, name)
    
    def restore_scopes(self):
        self.gen.push_var("MF$ExceptionHolder")
        self.gen.emit("pushscope")

class Avm2ilasm(object):
    """ AVM2 'assembler' generator routines """
    def __init__(self, abc_=None, make_script=True):
        self.abc = abc_ or abc.AbcFile()
        self.constants = self.abc.constants
        self.context = GlobalContext(self)
        if make_script:
            self.script0 = self.context.new_script()

    def _get_type(self, TYPE):
        return TYPE

    def get_class_context(self, name, DICT):
        return DICT.get(name, [None])[0]
    
    def I(self, *i):
        self.context.add_instructions(i)

    def M(self, multiname):
        return self.constants.multiname_pool.index_for(multiname)

    def SL(self, name):
        index = self.context.set_local(name)

        self.I(instructions.setlocal(index))
        return index

    def GL(self, name=None):
        index = self.context.get_local(name)
        self.I(instructions.getlocal(index))
        return index

    def KL(self, name):
        index = self.context.kill_local(name)
        self.I(instructions.kill(index))

    def HL(self, name):
        return self.context.has_local(name)
    
    def begin_class(self, name, super_name=None, bases=None):
        return self.context.new_class(name, super_name, bases)

    def begin_method(self, name, arglist, returntype, static=False, override=False):
        return self.context.new_method(name, arglist, returntype, static, override)

    def finish(self):
        while self.context:
            self.context = self.context.exit()
    
    # @property
    # def current_namespaces(self):
    #     context = self.scope
    #     namespaces = []
    #     while context is not None:
    #         namespaces += context.namespaces
    #         context = context.parent
    #     return namespaces
    
    def enter_context(self, ctx):
        self.context = ctx

    def exit_context(self):
        ctx = self.context
        self.context = ctx.exit()
        return ctx

    def current_class(self):
        context = self.context
        while context is not None:
            if context.CONTEXT_TYPE == "class":
                return context
            context = context.parent
        return None
    
    def pop(self, TYPE=None):
        self.I(instructions.pop())

    def dup(self, TYPE=None):
        self.I(instructions.dup())

    def swap(self):
        self.I(instructions.swap())

    def emit(self, instr, *args, **kwargs):
        self.I(instructions.INSTRUCTIONS[instr](*args, **kwargs))

    def set_label(self, label):
        self.emit('label', label)

    def branch_unconditionally(self, label):
        self.emit('jump', label)

    def branch_conditionally(self, iftrue, label):
        if iftrue:
            self.emit('iftrue', label)
        else:
            self.emit('iffalse', label)
    
    def call_function_constargs(self, name, *args):
        self.emit('findpropstrict', constants.QName(name))
        if args:
            self.load(*args)
        self.emit('callproperty', constants.QName(name), len(args))
    
    def load(self, v, *args):
        if hasattr(v, "multiname"):
            self.I(instructions.getlex(v.multiname()))
        else:
            self.push_const(v)

        for i in args:
            self.load(i)

    def store_var(self, name):
        self.SL(name)

    def store(self, v):
        self.store_var(v.name)
    
    # def prepare_call_oostring(self, OOTYPE):
    #     self.I(instructions.findpropstrict(types._str_qname))
    
    # def call_oostring(self, OOTYPE):
    #     self.I(instructions.callproperty(types._str_qname, 1))
        
    # call_oounicode = call_oostring
    # prepare_call_oounicode = prepare_call_oostring

    def newarray(self, TYPE, length=1):
        self.load(constants.QName("Array"))
        self.push_const(length)
        self.I(instructions.construct(1))

    def oonewarray(self, TYPE, length=1):
        TYPE = self._get_type(TYPE)
        _vec_qname = constants.packagedQName("__AS3__.vec", "Vector")
        self.load(_vec_qname)
        self.load(TYPE)
        self.I(instructions.applytype(1))
        self.load(length)
        self.I(instructions.construct(1))
        self.I(instructions.coerce(constants.TypeName(_vec_qname, TYPE)))
        
    def push_this(self):
        self.GL("this")
    
    def push_local(self, v):
        self.push_var(v.name)

    push_arg = push_local

    def push_var(self, v):
        self.GL(v)

    def push_const(self, v):
        if isinstance(v, (long, int)):
            if v > util.U32_MAX or v < -util.S32_MAX:
                self.I(instructions.pushdouble(
                        self.constants.double_pool.index_for(v)))
                if v > 0:
                    self.I(instructions.convert_u())
                else:
                    self.I(instructions.convert_i())
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

    def push_undefined(self, TYPE=None):
        self.I(instructions.pushundefined())

    def push_null(self, TYPE=None):
        self.I(instructions.pushnull())

    def init_array(self, members=None):
        if members:
            self.load(*members)
        self.I(instructions.newarray(len(members)))

    def init_object(self, members=None):
        if members:
            self.load(*chain(*members.iteritems()))
        self.I(instructions.newobject(len(members)))

    def init_vector(self, TYPE, members=None):
        if members:
            self.load(*members)
        self.oonewarray(TYPE, len(members))

    def set_field(self, TYPE, fieldname):
        self.emit('setproperty', constants.QName(fieldname))

    def new(self, TYPE):
        # XXX: assume no args for now
        TYPE = self._get_type(TYPE)
        self.emit('findpropstrict', TYPE)
        self.emit('constructprop', TYPE, 0)

    def downcast(self, TYPE):
        TYPE = self._get_type(TYPE)
        self.emit('coerce', TYPE)

    def begin_try(self):
        assert self.context.CONTEXT_TYPE == "method"
        self.context.code_start = len(self.context.asm)

    def end_try(self):
        assert self.context.CONTEXT_TYPE == "method"
        self.context.code_end = len(self.context.asm)

    def begin_catch(self, TYPE):
        assert self.context.CONTEXT_TYPE == "method"
        TYPE = self._get_type(TYPE).multiname()
        idx = self.context.add_exception(TYPE, "MF$ExceptionHolder")
        self.context.start_catch()
        self.context.set_local("MF$ExceptionHolder") # Reserve a spot for us.
        self.context.restore_scopes()
        self.context.enter_context(CatchContext(self, self.context))
        self.emit("newcatch", idx)
        self.dup()
        self.store_var("MF$ExceptionHolder")
        self.dup()
        self.emit("pushscope")
        
        self.swap()
        self.set_field("MF$ExceptionHolder")

    def end_catch(self):
        self.KL("MF$ExceptionHolder")
        self.emit("popscope")
