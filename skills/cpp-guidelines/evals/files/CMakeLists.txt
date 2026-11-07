cmake_minimum_required(VERSION 3.5)
project(geomlib)

set(CMAKE_CXX_FLAGS "-O3 -std=c++17")
include_directories(/usr/local/include /opt/vendor/include)
link_directories(/opt/vendor/lib)

file(GLOB SOURCES src/*.cpp)
add_library(geomlib ${SOURCES})
target_link_libraries(geomlib vendorcore)

add_executable(geom_tests tests/geom_tests.cpp)
target_link_libraries(geom_tests geomlib gtest)

# FetchContent of an unpinned branch
include(FetchContent)
FetchContent_Declare(fmt GIT_REPOSITORY https://github.com/fmtlib/fmt GIT_TAG master)
FetchContent_MakeAvailable(fmt)
target_link_libraries(geomlib fmt)

# no enable_testing(), no add_test(), no warning flags, no sanitizer option,
# no CMAKE_EXPORT_COMPILE_COMMANDS, no presets
