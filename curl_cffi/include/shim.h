#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define CURL_STATICLIB
#include "curl/curl.h"

typedef struct binary_string {
    size_t size;
    char* content;
} binary_string_t;

binary_string_t* make_string();
void free_string(binary_string_t* s);
int _curl_easy_setopt(void* curl, int option, void* param);
