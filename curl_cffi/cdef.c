typedef struct binary_string {
  size_t size;
  char *content;
} binary_string_t;

binary_string_t *make_string();
void free_string(binary_string_t *s);
void *curl_easy_init();
int _curl_easy_setopt(void *curl, int option, void *param);
int curl_easy_getinfo(void *curl, int option, void *ret);
int curl_easy_perform(void *curl);
void curl_easy_cleanup(void *curl);
char *curl_version();
int curl_easy_impersonate(void *curl, char *target, int default_headers);
struct curl_slist *curl_slist_append(struct curl_slist *list, char *string);
void curl_slist_free_all(struct curl_slist *list);
