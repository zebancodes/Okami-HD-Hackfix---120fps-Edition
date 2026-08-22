cmake_minimum_required(VERSION 3.20)
project(okami_hd_hackfix LANGUAGES C CXX)

option(OKAMI_TRACE "Build the per-frame key-state tracing variant" OFF)

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

add_library(dinput8_proxy SHARED src/dinput8_proxy.cpp src/mingw_guard_fix.c)
if(OKAMI_TRACE)
    target_compile_definitions(dinput8_proxy PRIVATE OKAMI_TRACE=1)
endif()
set_target_properties(
    dinput8_proxy PROPERTIES
    PREFIX ""
    OUTPUT_NAME "dinput8"
)

target_compile_definitions(dinput8_proxy PRIVATE WIN32_LEAN_AND_MEAN NOMINMAX)
target_compile_options(dinput8_proxy PRIVATE -O2 -Wall)
target_link_options(dinput8_proxy PRIVATE "-static-libgcc" "-static-libstdc++")

if(MINGW)
    # export DirectInput8Create from the DLL
    target_sources(dinput8_proxy PRIVATE src/dinput8_proxy.def)
endif()

# also copy the ini/readme alongside the DLL for convenience
add_custom_command(
    TARGET dinput8_proxy POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        "${CMAKE_SOURCE_DIR}/okami.ini"
        "${CMAKE_BINARY_DIR}/bin/okami.ini"
)
