
#include "shim.h"

#if defined(__ANDROID__)
// Provide glibc-style program name symbols for static libs expecting them.
// Android's bionic libc does not define these, so we supply safe defaults.
static char curl_cffi_progname[] = "python";
char *program_invocation_short_name = curl_cffi_progname;
char *program_invocation_name = curl_cffi_progname;

// glibc-only helpers occasionally referenced by third-party static libs
extern int *__errno(void);

int *__errno_location(void) {
    return __errno();
}

char *strchrnul(const char *s, int c) {
    char *p = strchr(s, c);
    return p ? p : (char *)s + strlen(s);
}

char *nl_langinfo(int item) {
    (void)item;
    return (char *)"";
}

void explicit_bzero(void *s, size_t n) {
    volatile unsigned char *p = (volatile unsigned char *)s;
    while (n--) {
        *p++ = 0;
    }
}

char *__gnu_strerror_r(int errnum, char *buf, size_t buflen) {
    if (buflen == 0) {
        return buf;
    }
    if (strerror_r(errnum, buf, buflen) != 0) {
        buf[0] = '\0';
    }
    return buf;
}
#endif

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
