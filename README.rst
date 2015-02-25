Introduction
============

PushBaby is a simple APNS library using gevent. PushBaby aims to
do the hard bits of APNS for you and no more. It handles:

 * Packing APNS messages into the binary payload format
 * Establishing and reestablishing SSL connections
 * Receiving and propagating errors to your application, asynchronously
 * Encoding pushes to JSON using efficient encoding
 * Truncating messages to fit APNS
 * Retrying pushes on nonfatal errors

PushBaby takes APNS payloads as dictionaries: it does not attempt to
construct them for you.

PushBaby does not load balance over multiple connections, although
this is something that would be considered in the future.

If you use PushBaby, remember that the rest of your application
must be gevent compatible, or you'll find PushBaby won't do
important things like receive errors.

Why PushBaby?
=============
There are many alternative APNS libraries for Python, for example:

applepushnotification
  https://github.com/martinkou/applepushnotification
  Similar, gevent-based library. Unmaintained.
apns
  https://github.com/djacobs/PyAPNs
  Uses pure python threads but will not always feed back errors if pushes can't
  be sent to the gateway.
pyapns
  https://github.com/samuraisam/pyapns/tree/master
  A full-featured XML-RPC HTTP-to-APNS server.
apns-clerk
  https://bitbucket.org/aleksihoffman/apns-clerk
  Fork of apns-client. Waits for error responses but means all calls to send a
  push block synchronously for some time.
APNSWrapper / HypnoAPNSWrapper
  https://code.google.com/p/apns-python-wrapper/
  Unmaintained. Uses openssl s_client.
apns-client
  https://bitbucket.org/sardarnl/apns-client
  Unmaintained
