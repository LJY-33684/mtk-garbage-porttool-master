import sys, platform

def retTypeAndMachine():
    # Detect machine and ostype
    ostype = platform.system().lower()
    if ostype.find("cygwin") >= 0:  # Support cygwin x11
        ostype = "windows"
    machine = platform.machine().lower()
    if machine == 'aarch64_be' \
        or machine == 'armv8b' \
        or machine == 'armv8l':
        machine = 'aarch64'
    if machine == 'i386' or machine == 'i686':
        machine = 'x86'
    if machine == "amd64":
        machine = 'x86_64'
    if ostype == 'windows':
        if not machine == 'x86_64':
            sys.stderr.write("Error : Program on windows only support 64bit machine\n")
            return None
    if ostype == 'linux':
        # 随包 bin/linux 只有 aarch64 与 x86_64 两套二进制；
        # 32 位 arm/x86 若放行会在后续找不到 magiskboot/openssl。
        if not (machine == 'aarch64' or machine == 'x86_64'):
            sys.stderr.write("Error : Linux only support 64bit machine [%s]\n" %machine)
            return None
    return ostype.replace('windows', 'win'), machine
