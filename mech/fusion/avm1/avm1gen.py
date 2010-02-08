
""" backend generator routines
"""

from collections import namedtuple

from mech.fusion.avm1 import actions, types_

ClassName = namedtuple("ClassName", "namespace classname")
Scope = namedtuple("Scope", "block parent callback islabel")

def make_variable(name):
    if isinstance(name, Variable):
        return name
    return Variable(name)

class StackDummy(object):
    def __init__(self, name):
        self.name = name

class Variable(StackDummy):
    def __str__(self):
        return 'Variable(name="%s")' % self.name
    __repr__ = __str__

    def __add__(self, other):
        if isinstance(other, StackDummy):
            other = other.name
        return Variable("ADD %r %r" % (self.name, other))

    def __radd__(self, other):
        return other + self

class ScriptObject(StackDummy):
    pass
    
class Function(StackDummy):
    pass

class AVM1Gen(object):
    """ AVM1 'assembler' generator routines """
    
    def __init__(self, block=None):
        self.stack = []
        self.namespaces = {}
        self.block = block or actions.Block(None, True)
        self.scope = Scope(self.block, None, None, False)
        self.action(self.block.constants)
        self.ilasm = self
    
    def new_label(self):
        return self.fn_block.new_label()

    def push_stack(self, *values):
        for element in values:
            self.stack.append(element)

    @property
    def fn_block(self):
        if self.scope.islabel:
            return self.scope.parent.block
        return self.scope.block
    
    def pop_stack(self, n=1):
        v = [self.stack.pop() for i in xrange(n)]
        return v
    
    def store_register(self, name, index=-1):
        index = self.fn_block.store_register(name, index)
        self.action(actions.ActionStoreRegister(index))
        return index
    
    def find_register(self, name):
        return self.fn_block.find_register(name)
    
    def action(self, action):
        return self.scope.block.add_action(action)
    
    def set_label(self, label):
        
        if self.scope.islabel:
            self.exit_scope()
            
        label, block = self._branch_start(label)
        self.enter_scope(block, islabel=True)   
    
    def enter_scope(self, new_code_obj, exit_callback=None, islabel=False):
        self.scope = Scope(new_code_obj, self.scope, exit_callback, islabel)
    
    def in_function(self):
        return self.fn_block.FUNCTION_TYPE
    
    def exit_scope(self):
        block_len = self.finalize_block(self.scope.block)
        exit_callback = self.scope.callback
        
        # Go up to the parent scope.
        self.scope = self.scope.parent
        
        self.scope.block.current_offset += block_len
        if exit_callback is not None:
            exit_callback()

    def finalize_block(self, block):
        for label, branch_block in block.branch_blocks:
            if not branch_block.sealed:
                branch_block.seal()
            
            # Set the label.
            block.labels[label] = block.current_offset
            
            # Add the actions, which updates current_offset
            for act in branch_block.actions:

                block.add_action(act)
        return block.seal()

    # def begin_namespace(self, _namespace):
    #     n = _namespace.split('.')
    #     namespace = self.namespaces
    #     if n[0] not in self.namespaces:
    #         self.namespaces[n[0]] = {}
    #         self.push_const(n[0])
    #         self.init_object()
    #         self.set_variable()
    #     self.push_var(n[0])
    #     for ns in n[1:]:
    #         if not ns in namespace:
    #             namespace[ns] = {}
    #             namespace = namespace[ns]
    #             self.push_const(ns)
    #             self.init_object()
    #             self.set_member()
    
    def begin_function(self, name, arglist):
        self.enter_scope(self.action(actions.ActionDefineFunction2(self.block, name, arglist)))
        
    def begin_static_method(self, function_name, _class, arglist):
        def exit_callback(block):
            self.set_member()
        self.load(_class)
        self.push_const(function_name)
        self.enter_scope(self.action(actions.ActionDefineFunction2(self.block, "", arglist, 0)), exit_callback)
        self.push_stack(Function(function_name))

    def begin_method(self, function_name, _class, arglist):
        def exit_callback(block):
            self.set_member()
        self.load(_class)
        self.push_const("prototype")
        self.get_member()
        self.push_const(function_name)
        self.enter_scope(self.action(actions.ActionDefineFunction2(self.block, "", arglist, 0)), exit_callback)
        self.push_stack(Function(function_name))
    
    def set_variable(self):
        value, name = self.pop_stack(2)
        if isinstance(name, Variable):
            name = name.name
        assert isinstance(name, basestring)
        if self.find_register(name) >= 0 and self.in_function() == 2:
            self.store_register(name)
        self.action(actions.ActionSetVariable())
        
    def get_variable(self):
        name, = self.pop_stack()
        self.action(actions.ActionGetVariable())
        self.push_stack(make_variable(name))
    
    def set_member(self):
        self.action(actions.ActionSetMember())
        value, name, obj = self.pop_stack(3)
        
    def get_member(self):
        self.action(actions.ActionGetMember())
        name, obj = self.pop_stack(2)
        self.push_stack(Variable("%s.%s" % (obj, name)))
        
    def push_reg_index(self, index):
        self.action(actions.ActionPush((index, types_.REGISTER)))
    
    def push_arg(self, v):
        assert self.in_function() > 0, "avm1gen::push_arg called while not in function scope."
        self.push_local(v)
    
    def push_var(self, v):
        k = self.find_register(v)
        print k
        if k >= 0:
            self.push_stack(Variable(v))
            self.push_reg_index(k)
        else:
            if self.in_function() == 2:
                if v in actions.preload:
                    setattr(self.scope.block, actions.preload[v])
                    self.scope.block.eval_flags()
                    return self.push_var(v)
            self.push_const(v)
            self.get_variable()
            if self.in_function() == 2:
                self.store_register(v)

    def push_this(self):
        self.push_var("this")
    
    def push_local(self, v):
        self.push_var(v.name)
        
    def push_const(self, *args):
        self.push_stack(*args)
        self.action(actions.ActionPush(types_.pytype_to_avm1(v) for v in args))
        
    def return_stmt(self):
        self.pop_stack()
        self.action(actions.ActionReturn())

    def swap(self):
        a, b = self.pop_stack(2)
        self.push_stack(b, a)
        self.action(actions.ActionSwap())
    
    def is_equal(self, value=None):
        if value is not None:
            self.push_const(value)
        self.action(actions.ActionEquals())
        self.pop_stack(2)

    def is_not_equal(self, value=None):
        self.is_equal(value)
        self.action(actions.ActionNot())
        self.pop_stack(2)
    
    def init_object(self, members={}):
        self.load(members.items())
        self.push_const(len(members))
        self.action(actions.ActionInitObject())
        self.pop_stack(self.pop_stack()[0])
        self.push_stack(ScriptObject("object"))

    def init_array(self, members=[]):
        self.load(members)
        self.push_const(len(members))
        self.action(actions.ActionInitArray())
        self.pop_stack(self.pop_stack()[0])
        self.push_stack(ScriptObject("array"))

    # Assumes the args and number of args are on the stack.
    def call_function(self, func_name):
        self.push_const(func_name)
        self.action(actions.ActionCallFunction())
        name, nargs = self.pop_stack()
        self.pop_stack(nargs)
        self.push_stack(Variable("%s_RETURN" % func_name))
    
    def call_function_constargs(self, func_name, *args):
        p = self.push_const(*reversed((func_name, len(args))+args))
        self.action(actions.ActionCallFunction())
        self.pop_stack(2+len(args))
        self.push_stack(Variable("%s_RETURN" % func_name))
        
    # Assumes the args and number of args and ScriptObject are on the stack.
    def call_method_n(self, func_name):
        self.load(func_name)
        self.action(actions.ActionCallMethod())
        name, obj, nargs = self.pop_stack(3)
        self.pop_stack(nargs)
        self.push_stack(Variable("%s.%s_RETURN" % (obj.name, name)))

    # Assumes the args and number of args are on the stack.
    def call_method_constvar(self, _class, func_name):
        self.push_var(_class)
        self.call_method_n(func_name)
    
    # Assumes the value is on the stack.
    # def set_proto_field(self, objname, member_name):
    #     self.push_const("prototype")
    #     self.push_var(objname)
    #     self.get_member()
    #     self.swap()
    #     self.push_const(member_name)
    #     self.swap()
    #     self.set_member()

    # Assumes the value is on the stack.
    # def set_static_field(self, objname, member_name):
    #     self.push_var(objname)
    #     self.swap()
    #     self.push_const(member_name)
    #     self.swap()
    #     self.set_member()

    # If no args are passed then it is assumed that the args and number of args are on the stack.
    def newobject_constthis(self, obj, *args):
        if len(args) > 0:
            self.load(args+(len(args), obj))
        else:
            self.load(obj)
        self.newobject()
        
    
    def newobject(self):
        self.action(avm1.ActionNewObject())
        name, nargs = self.pop_stack(2)
        args = self.pop_stack(nargs)
        self.push_stack(ScriptObject(name))
        
    # FIXME: will refactor later
    #load_str = load_const
    
    def begin_switch_varname(self, varname):
        self.push_var(varname)
        self.switch_register = self.store_register(varname)
    
    def write_case(self, testee):
        self.push_const(actions.RegisterByIndex(self.switch_register), testee)
        self.action(actions.ActionStrictEquals())
        self.pop_stack(2)
        if len(self.case_label) < 1:
            self.case_label, self.case_block = self.branch_if_true()
        else:
            self.branch_if_true(self.case_label)

    def write_break(self):
        self.exit_scope()
        self.case_flag = False
        self.case_block = None
    
    def enter_case_branch(self):
        self.enter_scope(self.case_block)
    
    def throw(self): # Assumes the value to be thrown is on the stack.
        self.action(actions.ActionThrow())
        self.pop_stack()
    
    # oosupport Generator routines
    def emit(self, op):
        a = actions.SHORT_ACTIONS[op]
        if a.push_count > 0:
            a.push_stack(StackDummy("Generated by %r" % op))
        elif a.push_count < 0:
            self.pop_stack(-a.push_count)
        self.action(a())
    
    def pop(self, TYPE):
        self.action(actions.ActionPop())
        self.pop_stack()

    def dup(self, TYPE):
        self.action(actions.ActionDuplicate())
        self.push_stack(*[self.pop_stack()] * 2)
        
    def load(self, v, *args):
        if isinstance(v, ClassName):
            if v.namespace:
                ns = v.namespace.split('.')
                self.push_var(ns[0])
                for i in ns[:0:-1]:
                    self.push_const(i)
                    self.get_member()
            else:
                self.push_var(v.classname)
        else:
            self.push_const(v)
        
        for i in args:
            self.load(v)
    
    def load_variable_hook(self, v):
        return False

    def _make_label(self, label):
        if label == "" or label is None:
            label = self.new_label()

        blocks = dict(self.fn_block.branch_blocks)
            
        if label in self.fn_block.branch_blocks:
            block = blocks[label]
        else:
            block = actions.Block(self.block, False)
            self.fn_block.branch_blocks.append((label, block))
        
        return (label, block)

    def _branch_start(self, label):
        return self._make_label(label)
    
    # Boolean value should be on stack when this is called
    def branch_unconditionally(self, label):
        label, block = self._branch_start(label)
        self.action(actions.ActionJump(label))
        return label, block

    def branch_conditionally(self, iftrue, label):
        label, block = self._branch_start(label)
        if not iftrue:
            self.action(actions.ActionNot())
        self.action(actions.ActionIf(label))
        self.pop_stack()
        return label, block

    def branch_if_true(self, label=None):
        return self.branch_conditionally(True, label)

    def branch_if_equal(self, label):
        label, block = self._branch_start(label)
        self.action(actions.ActionEquals())
        self.action(actions.ActionIf(label))
        self.pop_stack(2)
        return label, block

    def call_graph(self, graph):
        self.call_function(graph.func_name)

    def call_method(self, OOCLASS, method_name):
        pass

    def call_oostring(self, OOTYPE):
        self.action(actions.ActionConvertToString())

    call_oounicode = call_oostring

    def new(self, TYPE):
        pass
        #if isinstance(TYPE, ootype.List):
        #    self.oonewarray(None)
    
    def oonewarray(self, TYPE, length=1):
        self.newobject_constthis("Array", length)
    
    def push_null(self, TYPE=None):
        self.action(actions.ActionPush(types_.NULL))
        self.push_stack(types_.NULL)

    def push_undefined(self):
        self.action(actions.ActionPush(types_.UNDEFINED))
        self.push_stack(types_.UNDEFINED)

    def push_primitive_constant(self, TYPE, value):
        self.push_const(value)
