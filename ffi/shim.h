#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#define CURL_STATICLIB
#include "curl/curl.h"

int _curl_easy_setopt(void* curl, int option, void* param);
int _curl_easy_getinfo_socket(void* curl, int option, uintptr_t* result);
