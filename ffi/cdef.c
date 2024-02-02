// easy interfaces
void *curl_easy_init();
int _curl_easy_setopt(void *curl, int option, void *param);
int curl_easy_getinfo(void *curl, int option, void *ret);
int curl_easy_perform(void *curl);
void curl_easy_cleanup(void *curl);
void curl_easy_reset(void *curl);
int curl_easy_impersonate(void *curl, char *target, int default_headers);
void *curl_easy_duphandle(void *curl);

char *curl_version();

// slist interfaces
struct curl_slist {
   char *data;
   struct curl_slist *next;
};
struct curl_slist *curl_slist_append(struct curl_slist *list, char *string);
void curl_slist_free_all(struct curl_slist *list);

// callbacks
extern "Python" size_t buffer_callback(void *ptr, size_t size, size_t nmemb, void *userdata);
extern "Python" size_t write_callback(void *ptr, size_t size, size_t nmemb, void *userdata);
extern "Python" int debug_function(void *curl, int type, char *data, size_t size, void *clientp);

// multi interfaces
struct CURLMsg {
   int msg;       /* what this message means */
   void *easy_handle; /* the handle it concerns */
   union {
     void *whatever;    /* message-specific data */
     int result;   /* return code for transfer */
   } data;
};
void *curl_multi_init();
int curl_multi_cleanup(void *curlm);
int curl_multi_add_handle(void *curlm, void *curl);
int curl_multi_remove_handle(void *curlm, void *curl);
int curl_multi_socket_action(void *curlm, int sockfd, int ev_bitmask, int *running_handle);
int curl_multi_setopt(void *curlm, int option, void* param);
int curl_multi_assign(void *curlm, int sockfd, void *sockptr);
int curl_multi_perform(void *curlm, int *running_handle);
struct CURLMsg *curl_multi_info_read(void* curlm, int *msg_in_queue);

// multi callbacks
extern "Python" void socket_function(void *curl, int sockfd, int what, void *clientp, void *socketp);
extern "Python" void timer_function(void *curlm, int timeout_ms, void *clientp);

// websocket
struct curl_ws_frame {
  int age;              /* zero */
  int flags;            /* See the CURLWS_* defines */
  uint64_t offset;    /* the offset of this data into the frame */
  uint64_t bytesleft; /* number of pending bytes left of the payload */
  size_t len;
  ...;
};

int curl_ws_recv(void *curl, void *buffer, int buflen, int *recv, struct curl_ws_frame **meta);
int curl_ws_send(void *curl, void *buffer, int buflen, int *sent, int fragsize, unsigned int sendflags);

// mime
void *curl_mime_init(void* curl);  // -> form
void *curl_mime_addpart(void *form);  // -> part/field
int curl_mime_name(void *field, char *name);
int curl_mime_data(void *field, char *name, int datasize);
int curl_mime_type(void *field, char *type);
int curl_mime_filename(void *field, char *filename);
int curl_mime_filedata(void *field, char *filename);
void curl_mime_free(void *form);
