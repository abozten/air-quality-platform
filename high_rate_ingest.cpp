#include <curl/curl.h>
#include <iostream>
#include <thread>
#include <vector>
#include <random>
#include <chrono>
#include <atomic>
#include <sstream>
#include <getopt.h>

using namespace std;
using namespace std::chrono;

// --- Configuration Defaults ---
static int    DEFAULT_DURATION      = 30;     // seconds
static double DEFAULT_RATE          = 50.0;   // req/s
static int    DEFAULT_ANOMALY_CHANCE = 10;     // %
static string DEFAULT_ENDPOINT      = "http://localhost:8000/api/v1/air_quality/ingest";

atomic<uint64_t> REQUEST_COUNT(0);

double random_double(double min, double max, mt19937_64 &rng) {
    uniform_real_distribution<double> dist(min, max);
    return dist(rng);
}

struct ParamRange {
    double normal_min, normal_max;
    double anomaly_min, anomaly_max;
};

int main(int argc, char** argv) {
    // --- Parse command-line options ---
    int    test_duration = DEFAULT_DURATION;
    double rate          = DEFAULT_RATE;
    int    anomaly_chance = DEFAULT_ANOMALY_CHANCE;
    string api_endpoint  = DEFAULT_ENDPOINT;
    int    threads       = thread::hardware_concurrency();

    const struct option long_opts[] = {
        {"duration",      required_argument, nullptr, 'd'},
        {"rate",          required_argument, nullptr, 'r'},
        {"anomaly-chance",required_argument, nullptr, 'a'},
        {"endpoint",      required_argument, nullptr, 'e'},
        {"threads",       required_argument, nullptr, 't'},
        {"help",          no_argument,       nullptr, 'h'},
        {nullptr,          0,                 nullptr,  0 }
    };
    int opt;
    while ((opt = getopt_long(argc, argv, "d:r:a:e:t:h", long_opts, nullptr)) != -1) {
        switch (opt) {
            case 'd': test_duration = stoi(optarg); break;
            case 'r': rate          = stod(optarg); break;
            case 'a': anomaly_chance = stoi(optarg); break;
            case 'e': api_endpoint  = optarg;      break;
            case 't': threads       = stoi(optarg); break;
            case 'h':
            default:
                cout << "Usage: " << argv[0]
                     << " [--duration sec] [--rate req/s] [--anomaly-chance %]"
                     << " [--endpoint URL] [--threads n]\n";
                return 0;
        }
    }

    cout << "Starting load test:\n"
         << "  Duration: " << test_duration << "s\n"
         << "  Rate: "     << rate          << " req/s\n"
         << "  Anomaly: "  << anomaly_chance << "%\n"
         << "  Threads: "  << threads       << "\n"
         << "  Endpoint: " << api_endpoint  << "\n";

    // Prepare parameter ranges
    vector<string> params = {"pm25","pm10","no2","so2","o3"};
    vector<ParamRange> ranges = {
        {5.0, 80.0, 250.1, 500.0},    // pm25
        {10.0, 150.0, 420.1, 800.0},  // pm10
        {10.0, 100.0, 200.1, 400.0},  // no2
        {1.0, 20.0, 50.1, 150.0},     // so2
        {20.0, 180.0, 240.1, 400.0}   // o3
    };

    // Initialize CURL globally
    curl_global_init(CURL_GLOBAL_ALL);

    // Calculate rate per thread
    double rate_per_thread = rate / threads;
    double sleep_sec = 1.0 / rate_per_thread;

    auto start_time = steady_clock::now();
    auto end_time   = start_time + seconds(test_duration);

    // Worker lambda
    auto worker = [&](int tid) {
        random_device rd;
        mt19937_64 rng(rd() ^ (tid << 1));
        uniform_int_distribution<int> param_idx_dist(0, params.size()-1);
        uniform_int_distribution<int> anomaly_dist(0, 99);

        CURL *curl = curl_easy_init();
        struct curl_slist *headers = nullptr;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_URL, api_endpoint.c_str());
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
        curl_easy_setopt(curl, CURLOPT_POST, 1L);

        while (steady_clock::now() < end_time) {
            double lat = random_double(35.81, 42.10, rng);
            double lon = random_double(25.66, 44.82, rng);
            int idx    = param_idx_dist(rng);
            bool is_anomaly = (anomaly_dist(rng) < anomaly_chance);
            ParamRange &pr = ranges[idx];
            double value = is_anomaly
                ? random_double(pr.anomaly_min, pr.anomaly_max, rng)
                : random_double(pr.normal_min, pr.normal_max, rng);

            ostringstream oss;
            oss << "{"
                << "\"latitude\":" << lat << ","
                << "\"longitude\":"<< lon << ","
                << "\""<< params[idx] <<"\":"<< value
                << "}";
            string json = oss.str();

            curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json.c_str());
            curl_easy_perform(curl);
            REQUEST_COUNT.fetch_add(1, memory_order_relaxed);

            this_thread::sleep_for(duration<double>(sleep_sec));
        }

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
    };

    vector<thread> pool;
    for (int i = 0; i < threads; ++i) {
        pool.emplace_back(worker, i);
    }
    for (auto &t : pool) t.join();

    curl_global_cleanup();

    auto actual_dur = duration_cast<seconds>(steady_clock::now() - start_time).count();
    cout << "Finished: sent " << REQUEST_COUNT.load() << " requests in "
         << actual_dur << " seconds." << endl;
    return 0;
}
