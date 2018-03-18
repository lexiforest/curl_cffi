#include <stdlib.h>
#include <stdio.h>
#include <cstring>
#define CURL_STATICLIB
#include <curl/curl.h>

typedef struct binary_string {
    size_t size;
    char* content;
    ~binary_string() {
        if (content) {
            free(content);
        }
    }
} binary_string_t;

typedef struct curl_instance {
    void* curl;
} curl_instance_t;

// Bindings
binary_string_t* make_string();
void free_string(binary_string_t* obj);
curl_instance_t* bind_curl_easy_init();
int bind_curl_easy_setopt(curl_instance_t* instance, int option, void* parameter);
int bind_curl_easy_getinfo(curl_instance_t* instance, int option, void* retValue);
int bind_curl_easy_perform(curl_instance_t* instance);
void bind_curl_easy_cleanup(curl_instance_t* instance);
