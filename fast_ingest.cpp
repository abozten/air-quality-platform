#include <curl/curl.h>
#include <iostream>
#include <thread>
#include <vector>
#include <random>
#include <chrono>
#include <atomic>
#include <sstream>
#include <getopt.h>
#include <iomanip>

using namespace std;
using namespace std::chrono;

// --- Configuration Defaults ---
static int    DEFAULT_DURATION      = 30;     // seconds
static double DEFAULT_RATE          = 50.0;   // req/s
static int    DEFAULT_ANOMALY_CHANCE = 10;    // %
static string DEFAULT_ENDPOINT      = "http://localhost:8000/api/v1/air_quality/ingest";

atomic<uint64_t> REQUEST_COUNT(0);

// Discard API response to prevent printing
static size_t write_callback(void*, size_t size, size_t nmemb, void*) {
    return size * nmemb; // Accept all data, discard it
}

double random_double(double min, double max, mt19937_64 &rng) {
    uniform_real_distribution<double> dist(min, max);
    return dist(rng);
}

struct ParamRange {
    double normal_min, normal_max;
    double anomaly_min, anomaly_max;
};

// Structure to hold lat/lon pairs
struct Coord {
    double latitude;
    double longitude;
};

// Generate a grid of coordinates covering Europe with ~50 km spacing
vector<Coord> generate_europe_grid() {
    vector<Coord> grid;
    const double lat_min = 35.0, lat_max = 70.0;  // Europe's latitude bounds
    const double lon_min = -25.0, lon_max = 40.0; // Europe's longitude bounds
    const double step = 0.45;                     // ~50 km in degrees

    for (double lat = lat_min; lat <= lat_max; lat += step) {
        for (double lon = lon_min; lon <= lon_max; lon += step) {
            grid.push_back(Coord{lat, lon});
        }
    }
    return grid;
}

// Progress bar function
void print_progress(int duration, steady_clock::time_point start_time, steady_clock::time_point end_time) {
    const int bar_width = 50;
    while (steady_clock::now() < end_time) {
        auto elapsed = duration_cast<seconds>(steady_clock::now() - start_time).count();
        float progress = min(1.0f, static_cast<float>(elapsed) / duration);
        int pos = static_cast<int>(bar_width * progress);

        cout << "\r[";
        for (int i = 0; i < bar_width; ++i) {
            if (i < pos) cout << "=";
            else cout << " ";
        }
        cout << "] " << fixed << setprecision(1) << progress * 100.0 << "%";
        cout.flush();

        this_thread::sleep_for(milliseconds(1000)); // Update every second
    }
    // Print final 100% when done
    cout << "\r[";
    for (int i = 0; i < bar_width; ++i) cout << "=";
    cout << "] 100.0%" << endl;
}

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
    vector<string> params = {"pm25", "pm10", "no2", "so2", "o3"};
    vector<ParamRange> ranges = {
        {5.0, 80.0, 250.1, 500.0},    // pm25
        {10.0, 150.0, 420.1, 800.0},  // pm10
        {10.0, 100.0, 200.1, 400.0},  // no2
        {1.0, 20.0, 50.1, 150.0},     // so2
        {20.0, 180.0, 240.1, 400.0}   // o3
    };

    // Generate coordinate grid
    vector<Coord> grid = generate_europe_grid();
    cout << "Generated " << grid.size() << " coordinate points for Europe.\n";

    // Initialize CURL globally
    curl_global_init(CURL_GLOBAL_ALL);

    // Calculate rate per thread
    double rate_per_thread = rate / threads;
    double sleep_sec = 1.0 / rate_per_thread;

    auto start_time = steady_clock::now();
    auto end_time   = start_time + seconds(test_duration);

    // Start progress bar thread
    thread progress_thread(print_progress, test_duration, start_time, end_time);

    // Worker lambda
    auto worker = [&](int tid) {
        random_device rd;
        mt19937_64 rng(rd() ^ (tid << 1));
        uniform_int_distribution<int> anomaly_dist(0, 99);

        // Divide grid points among threads
        size_t points_per_thread = grid.size() / threads;
        size_t start_idx = tid * points_per_thread;
        size_t end_idx = (tid == threads - 1) ? grid.size() : start_idx + points_per_thread;

        CURL* curl = curl_easy_init();
        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_URL, api_endpoint.c_str());
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 5L);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, 10L);
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback); // Discard response

        size_t coord_index = start_idx;
        while (steady_clock::now() < end_time) {
            // Cycle through assigned points
            if (coord_index >= end_idx) {
                coord_index = start_idx;
            }
            Coord coord = grid[coord_index];
            coord_index++;

            // Generate values for all parameters
            ostringstream oss;
            oss << "{"
                << "\"latitude\":" << coord.latitude << ","
                << "\"longitude\":" << coord.longitude;
            for (size_t i = 0; i < params.size(); ++i) {
                bool is_anomaly = (anomaly_dist(rng) < anomaly_chance);
                ParamRange& pr = ranges[i];
                double value = is_anomaly
                    ? random_double(pr.anomaly_min, pr.anomaly_max, rng)
                    : random_double(pr.normal_min, pr.normal_max, rng);
                oss << ",\"" << params[i] << "\":" << value;
            }
            oss << "}";
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
    for (auto& t : pool) {
        t.join();
    }

    // Wait for progress thread to finish
    progress_thread.join();

    curl_global_cleanup();

    auto actual_dur = duration_cast<seconds>(steady_clock::now() - start_time).count();
    cout << "Finished: sent " << REQUEST_COUNT.load() << " requests in "
         << actual_dur << " seconds." << endl;
    return 0;
}