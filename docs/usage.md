Usage
=====

Installation
------------

To use curl_cffi, first install it using pip:

```console
(.venv) $ pip install curl_cffi
```

Creating recipes
----------------

To retrieve a list of random ingredients, you can use the
`lumache.get_random_ingredients()` function:

::: curl_cffi.requests
    options:
      show_root_heading: true

<br>

The `kind` parameter should be either `"meat"`, `"fish"`, or `"veggies"`.
Otherwise, [`get_random_ingredients`][curl_cffi.requests] will raise an exception [`lumache.InvalidKindError`](/api#lumache.InvalidKindError).

For example:

```python
>>> import lumache
>>> lumache.get_random_ingredients()
['shells', 'gorgonzola', 'parsley']
```

## API

Requests: almost the same as requests.

Curl object:

* `setopt(CurlOpt, value)`: Sets curl options as in `curl_easy_setopt`
* `perform()`: Performs curl request, as in `curl_easy_perform`
* `getinfo(CurlInfo)`: Gets information in response after curl perform, as in `curl_easy_getinfo`
* `close()`: Closes and cleans up the curl object, as in `curl_easy_cleanup`

Enum values to be used with `setopt` and `getinfo`, and can be accessed from `CurlOpt` and `CurlInfo`.

