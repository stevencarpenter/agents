#include <gtest/gtest.h>
#include <chrono>
#include <iostream>
#include <thread>
#include "geom/polygon.hpp"
#include "geom/parser.hpp"

TEST(Polygon, AreaWorks) {
    geom::Polygon p = geom::parse("0,0 4,0 4,3");
    std::cout << p.area() << std::endl;
    EXPECT_TRUE(p.area() > 0);
}

TEST(Polygon, AreaWorksAgain) {
    geom::Polygon p = geom::parse("0,0 4,0 4,3");
    EXPECT_TRUE(p.area() > 0);
}

TEST(Polygon, DebugString) {
    geom::Polygon p = geom::parse("0,0 1,0 1,1");
    EXPECT_EQ(p.toString(), "Polygon{(0,0),(1,0),(1,1)} area=0.5000000");
}

TEST(Polygon, ParsesAsync) {
    geom::Polygon p;
    std::thread t([&] { p = geom::parse("0,0 4,0 4,3"); });
    std::this_thread::sleep_for(std::chrono::seconds(2));
    t.join();
    EXPECT_EQ(p.vertexCount(), 3);
}

TEST(Polygon, DISABLED_HugeInput) {
    geom::Polygon p = geom::parse(std::string(10'000'000, '1'));
    EXPECT_GT(p.vertexCount(), 0);
}

TEST(Polygon, EmptyInputThrows) {
    try {
        geom::parse("");
        FAIL();
    } catch (const std::exception& e) {
        EXPECT_STREQ(e.what(), "parse error: empty input at offset 0");
    }
}

TEST(Polygon, FloatEquality) {
    geom::Polygon p = geom::parse("0,0 1,0 1,1");
    EXPECT_EQ(p.area(), 0.5);
}
