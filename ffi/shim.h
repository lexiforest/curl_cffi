#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define CURL_STATICLIB
#include "curl/curl.h"

int _curl_easy_setopt(void* curl, int option, void* param);
int _curl_share_setopt(void* share, int option, void* param);
