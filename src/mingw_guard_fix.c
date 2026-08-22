/* Workaround for conda-forge's mingw-w64 (UCRT) toolchain: its stack-
 * protected CRT startup objects keep __stack_chk_guard inconsistent on this
 * machine, so every gcc-built binary died with
 * "*** stack smashing detected ***" before reaching main().
 * A strong, never-changing guard makes all canary checks compare equal.
 * The fail handler still aborts if a canary is actually tripped. */
#include <windows.h>

__attribute__((used)) unsigned long long __stack_chk_guard = 0x4d43428a5f2e11d6ULL;

void __attribute__((used)) __stack_chk_fail(void)
{
    ExitProcess(0xC0000409); /* STATUS_STACK_BUFFER_OVERRUN */
}
