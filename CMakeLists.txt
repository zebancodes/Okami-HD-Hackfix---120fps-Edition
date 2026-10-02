cmake_minimum_required(VERSION 3.21)
project(okami_hd_hackfix LANGUAGES C CXX)

option(OKAMI_TRACE "Build the per-frame tracing variant (gcc/clang only)" OFF)
option(OKAMI_DIAG "Build the game-speed diagnostics variant (gcc/clang only)" OFF)
option(OKAMI_TRACER "Build the animation tracer" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
# Static CRT for MSVC-style toolchains (cl, clang-cl, clang targeting MSVC) so
# the DLL has no vcruntime dependency in the game folder.
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

add_library(dinput8_proxy SHARED src/dinput8_proxy.cpp)
if(MINGW)
    # conda-forge mingw-w64 CRT stack-canary workaround
    target_sources(dinput8_proxy PRIVATE src/mingw_guard_fix.c)
endif()
if(OKAMI_TRACE)
    target_compile_definitions(dinput8_proxy PRIVATE OKAMI_TRACE=1)
endif()
if(OKAMI_DIAG)
    target_compile_definitions(dinput8_proxy PRIVATE OKAMI_DIAG=1)
endif()
if(OKAMI_TRACER)
    # the stub pool is generated from the installed main.dll, not checked in
    if(NOT EXISTS "${CMAKE_SOURCE_DIR}/src/generated/tracer_sites.h")
        message(FATAL_ERROR "src/generated/tracer_sites.h is missing: run "
                            "python tools/gen_tracer.py, then python tools/verify_tracer.py")
    endif()
    target_compile_definitions(dinput8_proxy PRIVATE OKAMI_TRACER=1)
endif()
set_target_properties(
    dinput8_proxy PROPERTIES
    PREFIX ""
    OUTPUT_NAME "dinput8"
)

target_compile_definitions(dinput8_proxy PRIVATE
    WIN32_LEAN_AND_MEAN NOMINMAX _CRT_SECURE_NO_WARNINGS)
target_link_libraries(dinput8_proxy PRIVATE user32 winmm)

if(MSVC)
    # cl.exe / clang-cl
    target_compile_options(dinput8_proxy PRIVATE /W4 /O2)
else()
    # gcc / clang (GNU-style driver)
    target_compile_options(dinput8_proxy PRIVATE -O2 -Wall -Wextra)
endif()
if(MINGW)
    target_link_options(dinput8_proxy PRIVATE
        "-static" "-static-libgcc" "-static-libstdc++")
endif()

# copy the ini alongside the DLL for convenience
add_custom_command(
    TARGET dinput8_proxy POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/okami.ini"
        "$<TARGET_FILE_DIR:dinput8_proxy>/okami.ini"
)
