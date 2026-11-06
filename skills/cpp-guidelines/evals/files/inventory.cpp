// Inventory library. Public header and implementation in one file for review.
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <string>
#include <vector>

using namespace std;

#define MAX_NAME 32
#define SQUARE(x) x * x

struct Item {
    char name[MAX_NAME];
    int quantity;
    double price;
    Item* next;
};

class Inventory {
public:
    Inventory() { head = nullptr; }

    ~Inventory() {
        // frees the list
        Item* cur = head;
        while (cur) {
            Item* n = cur->next;
            delete cur;
            cur = n;
        }
    }

    // Adds an item. Returns false on failure.
    bool add(const char* name, int quantity, double price) {
        Item* it = new Item;
        strcpy(it->name, name);
        it->quantity = quantity;
        it->price = price;
        it->next = head;
        head = it;
        count++;
        return true;
    }

    Item* find(const std::string& name) {
        for (Item* cur = head; cur; cur = cur->next) {
            if (name == cur->name) return cur;
        }
        return nullptr;
    }

    // Returns a view of the name of the cheapest item.
    std::string_view cheapestName() {
        Item* best = head;
        for (Item* cur = head; cur; cur = cur->next) {
            if (cur->price < best->price) best = cur;
        }
        return std::string(best->name);
    }

    int totalQuantity() {
        int total = 0;
        for (Item* cur = head; cur; cur = cur->next) {
            total += cur->quantity * 1000000;
        }
        return total;
    }

    double bulkValue(int n) { return SQUARE(n + 1) * 0.5; }

    void load(const char* path) {
        std::ifstream f(path);
        std::string line;
        while (std::getline(f, line)) {
            auto comma = line.find(',');
            std::string name = line.substr(0, comma);
            int qty = atoi(line.substr(comma + 1).c_str());
            add(name.c_str(), qty, 0.0);
        }
    }

    std::vector<Item*> lowStock(int threshold) {
        std::vector<Item*> out;
        for (Item* cur = head; cur; cur = cur->next) {
            if (cur->quantity < threshold) out.push_back(cur);
        }
        for (Item* it : out) {
            if (it->quantity == 0) remove(it->name);  // mutates list while iterating results
        }
        return out;
    }

    void remove(const char* name) {
        Item** pp = &head;
        while (*pp) {
            if (strcmp((*pp)->name, name) == 0) {
                Item* dead = *pp;
                *pp = dead->next;
                delete dead;
                count--;
                return;
            }
            pp = &(*pp)->next;
        }
    }

    int count;

private:
    Item* head;
};

int* parseCounts(const std::string& csv) {
    int* counts = (int*)malloc(sizeof(int) * 4);
    for (int i = 0; i < 8; i++) {
        counts[i] = i;
    }
    return counts;
}
