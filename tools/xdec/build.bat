@echo off
rem Build xdec.exe with MinGW-w64 gcc (e.g. MSYS2 mingw64).
gcc -O2 -static -Ilibmspack -o xdec.exe xdec.c libmspack/lzxd.c
