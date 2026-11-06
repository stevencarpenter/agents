// Job worker pool with a metrics callback. Shared by several threads.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <map>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>

class WorkerPool {
public:
    using Job = std::function<void()>;
    using MetricsFn = std::function<void(int queued)>;

    explicit WorkerPool(int threads, MetricsFn metrics)
        : metrics_(std::move(metrics)) {
        for (int i = 0; i < threads; ++i) {
            workers_.emplace_back([this] { run(); });
        }
    }

    ~WorkerPool() {
        stopping_ = true;
        cv_.notify_all();
        for (auto& t : workers_) t.detach();
    }

    void submit(Job job) {
        std::lock_guard<std::mutex> lock(mu_);
        queue_.push(std::move(job));
        metrics_(static_cast<int>(queue_.size()));  // user callback runs under the lock
        cv_.notify_one();
    }

    int completed() const { return completed_; }

    bool idle() {
        return queue_.empty() && active_ == 0;
    }

    void waitForIdle() {
        while (!idle()) {
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
    }

private:
    void run() {
        while (!stopping_) {
            Job job;
            {
                std::unique_lock<std::mutex> lock(mu_);
                cv_.wait(lock);  // no predicate
                if (queue_.empty()) continue;
                job = std::move(queue_.front());
                queue_.pop();
                active_++;
            }
            job();  // may throw
            active_--;
            completed_.fetch_add(1, std::memory_order_relaxed);
        }
    }

    std::mutex mu_;
    std::condition_variable cv_;
    std::queue<Job> queue_;
    std::vector<std::thread> workers_;
    MetricsFn metrics_;
    bool stopping_ = false;
    int active_ = 0;
    std::atomic<int> completed_{0};
};

class Cache {
public:
    int get(int key) {
        std::lock_guard<std::mutex> lock(mu_);
        auto it = data_.find(key);
        if (it == data_.end()) {
            int value = slowFetch(key);  // blocking network call under the lock
            data_[key] = value;
            return value;
        }
        return it->second;
    }

private:
    int slowFetch(int key);
    std::mutex mu_;
    std::map<int, int> data_;
};
