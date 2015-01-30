import json.encoder

# May as well cache a JSON encoder because we'll be
# using the same altered configuration each time
# (the json module will otherwise create it each time)
#
# The supplied encoding here is 'utf8': with no hyphen.
# Both are the same encoding as far as core python is
# concerned, but the python json module special cases
# on =='utf-8'. The special cased code, however, has a
# bug whereby, if supplied with a mix of unicode objects
# and non-ascii 'str' objects (and using
# ensure_ascii=False), it will break because it passes
# both together in an array to string.join which is
# invalid.
#
# In reality, we always convert text we know about
# to unicode in truncation so this shouldn't be an
# issue, but it could break if Apple add other
# text fields we don't handle
jsonencoder = json.encoder.JSONEncoder(
    ensure_ascii=False,
    encoding='utf8',  # 'utf8' != 'utf-8' here, see above
    separators=(',', ':')
)


def json_for_payload(payload):
    return jsonencoder.encode(payload).encode('utf8')
