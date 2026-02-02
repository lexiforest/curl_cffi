
#include "shim.h"

int _curl_easy_setopt(void* curl, int option, void* parameter) {
    // printf("****** hijack test begins: \n");
    // int val = curl_easy_setopt(instance->curl, CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_2_0);
    // printf("****** hijack test ends. opt: %d, val: %d, result is: %d\n", CURLOPT_HTTP_VERSION, CURL_HTTP_VERSION_2_0, val);
    // CURLoption opt_value = (CURLoption) option;
    // printf("option: %d, setopt parameter: %d\n", option, *(int*)parameter);
    // for integer options, we need to convert param from pointers to integers
    if (option < CURLOPTTYPE_OBJECTPOINT) {
        return (int)curl_easy_setopt(curl, (CURLoption)option, *(long*)parameter);
    }
    if (CURLOPTTYPE_OFF_T <= option && option < CURLOPTTYPE_BLOB) {
        return (int)curl_easy_setopt(curl, (CURLoption)option, *(curl_off_t*)parameter);
    }
    return (int)curl_easy_setopt(curl, (CURLoption)option, parameter);
}
