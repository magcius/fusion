# test_complex assumes you have 'avmshell' on your PATH.

import subprocess

from py.path import local
from fusion.avm2.loadable import Local
from fusion.avm2.abc_ import AbcFile

tmpdir = local.make_numbered_dir("fusion-session-")

def interpret(gen, tmpfile):
    # Epilogue
    gen.call_function("print", [Local("result")])
    gen.finish()

    tmpfile.write(gen.abc.serialize(), mode='wb')

    procargs = ['avmshell', '-Dinterp', str(tmpfile)]
    testproc = subprocess.Popen(procargs, stdout=subprocess.PIPE)
    result = testproc.stdout.read()
    result = result.rstrip("\n")
    return result

def pytest_funcarg__gen(request):
    abcfile = AbcFile()
    gen = abcfile.create_generator()
    script = gen.begin_script()
    init = script.make_init()
    gen.enter_rib(init)
    return gen

def pytest_funcarg__tmpfile(request):
    filename = request.function.func_name + '.abc'
    return tmpdir.join(filename)

def test_add(gen, tmpfile):
    gen.load(1)
    gen.load(2)
    gen.emit('add')
    gen.store_var("result")

    result = interpret(gen, tmpfile)
    assert result == '3'
