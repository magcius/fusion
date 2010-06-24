***********************
codegenerator interface
***********************
:mod:`mech.fusion.avm2.codegen`
===============================

.. automodule:: mech.fusion.avm2.codegen

Code Generator
--------------
.. autoclass:: CodeGenerator
   :show-inheritance:

Entering and Exiting Contexts
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
.. automethod:: CodeGenerator.enter_context
.. automethod:: CodeGenerator.exit_context
.. automethod:: CodeGenerator.exit_until
.. automethod:: CodeGenerator.exit_until_type
.. automethod:: CodeGenerator.current_class

Context Creation
^^^^^^^^^^^^^^^^

Functional
~~~~~~~~~~
.. automethod:: CodeGenerator.begin_method
.. automethod:: CodeGenerator.end_method
.. automethod:: CodeGenerator.begin_constructor
.. automethod:: CodeGenerator.end_constructor
.. automethod:: CodeGenerator.begin_class
.. automethod:: CodeGenerator.end_class

Context Manager
~~~~~~~~~~~~~~~
.. automethod:: CodeGenerator.Method
.. automethod:: CodeGenerator.Constructor
.. automethod:: CodeGenerator.Class

Stack Operations
^^^^^^^^^^^^^^^^

Basic Operations
~~~~~~~~~~~~~~~~
.. automethod:: CodeGenerator.pop
.. automethod:: CodeGenerator.dup
.. automethod:: CodeGenerator.throw
.. automethod:: CodeGenerator.swap

Locals and Arguments
~~~~~~~~~~~~~~~~~~~~
.. automethod:: CodeGenerator.push_var
.. automethod:: CodeGenerator.push_arg
.. automethod:: CodeGenerator.store_var
.. automethod:: CodeGenerator.HL
.. automethod:: CodeGenerator.KL

Pushing Constants
~~~~~~~~~~~~~~~~~
.. automethod:: CodeGenerator.push_this
.. automethod:: CodeGenerator.push_true
.. automethod:: CodeGenerator.push_false
.. automethod:: CodeGenerator.push_undefined
.. automethod:: CodeGenerator.push_null

Loadables
~~~~~~~~~
.. automethod:: CodeGenerator.load

.. autoclass:: Argument
   :members:

.. autoclass:: Local
   :members:

Other
~~~~~~
.. automethod:: CodeGenerator.isinstance
.. automethod:: CodeGenerator.gettype
.. automethod:: CodeGenerator.downcast
.. automethod:: CodeGenerator.init_object
.. automethod:: CodeGenerator.init_array
.. automethod:: CodeGenerator.init_vector
.. automethod:: CodeGenerator.set_field
.. automethod:: CodeGenerator.get_field

Try/Catch
^^^^^^^^^
.. automethod:: CodeGenerator.begin_try
.. automethod:: CodeGenerator.end_try
.. automethod:: CodeGenerator.begin_catch
.. automethod:: CodeGenerator.end_catch
.. automethod:: CodeGenerator.push_exception

Calling Functions
^^^^^^^^^^^^^^^^^
.. automethod:: CodeGenerator.call_function_constargs
.. automethod:: CodeGenerator.call_method_constargs
.. automethod:: CodeGenerator.call_function
.. automethod:: CodeGenerator.call_method

Branching and Labels
^^^^^^^^^^^^^^^^^^^^
.. automethod:: CodeGenerator.set_label
.. automethod:: CodeGenerator.branch_unconditionally
.. automethod:: CodeGenerator.branch_conditionally
.. automethod:: CodeGenerator.branch_if_true
.. automethod:: CodeGenerator.branch_if_false
.. automethod:: CodeGenerator.branch_if_equal
.. automethod:: CodeGenerator.branch_if_not_equal
.. automethod:: CodeGenerator.branch_if_strict_equal
.. automethod:: CodeGenerator.branch_if_strict_not_equal
.. automethod:: CodeGenerator.branch_if_greater_than
.. automethod:: CodeGenerator.branch_if_greater_equals
.. automethod:: CodeGenerator.branch_if_less_than
.. automethod:: CodeGenerator.branch_if_less_equals
.. automethod:: CodeGenerator.branch_if_not_greater_than
.. automethod:: CodeGenerator.branch_if_not_greater_equals
.. automethod:: CodeGenerator.branch_if_not_less_than
.. automethod:: CodeGenerator.branch_if_not_less_equals

Nodes
^^^^^
.. automethod:: CodeGenerator.add_node

Internal API
^^^^^^^^^^^^
.. automethod:: CodeGenerator._get_type
.. automethod:: CodeGenerator._get_vector_type
.. automethod:: CodeGenerator.get_class_context

Contexts
--------

Contexts are used by the code generator to keep track of state and to
keep the data of individual components it is creating.

.. autoclass:: GlobalContext
   :members:
   :show-inheritance:

.. autoclass:: ScriptContext
   :members:
   :show-inheritance:

.. autoclass:: ClassContext
   :members:
   :show-inheritance:

.. autoclass:: MethodContext
   :members:
   :show-inheritance:
