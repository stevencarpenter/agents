cmake_minimum_required(VERSION 3.10)
project(stackq C)

set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} -g -O0")

add_library(stackq src/stackq.c)
target_include_directories(stackq PUBLIC include)

add_executable(stackq_test tests/test_stackq.c)
target_link_libraries(stackq_test stackq)

# Tests are run by hand: ./stackq_test
# No add_test(), no enable_testing().

install(TARGETS stackq DESTINATION lib)
install(FILES include/stackq.h DESTINATION include)
