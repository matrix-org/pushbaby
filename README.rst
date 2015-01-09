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

