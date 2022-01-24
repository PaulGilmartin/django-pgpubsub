# Design Notes

# Introduction

This PR introduces the first working sketch of the django-pubsub library
(still not sure about the name).
It focuses on developing the beginnings of the user facing interface and basic
mechanics of the python implementation of the postgres notify-listen protocol.
We do not focus on the trickier topics of dealing with concurrency and
listener durability.

No design in here is by any means set in stone and very happy to clarify/change/discuss
any aspect of this if there's a better idea out there. There are also a number
of open questions/ideas for improvement listed throughout this doc/in comments
in the code.

I have tested as much as possible without having postgres to unit test over.
There will still be a lot of bugs and probably code which could be refactored
and improved.
The examples below are actually working examples at least.


# Documentation/Notes via Examples
Here we show how a user can use django-pubsub to set up and notify listeners
to process functions async. We'll make use of the models and relationships
defined in the tests app.

We focus on two use cases:
- The first is where the user defines a listener with custom keyword arguments and notifies
  that listener manually.
- The second is where the user defines a listener which is notified whenever some django-pgtrigger is executed.

Fully working versions of these examples can be found in the `tests` app.

## Custom Listen and Manual Notify

In this example, we wish to maintain a cache of how frequently
Post objects are read per day. We want to defer this caching logic
to another process so as not to hurt read performance times for posts.
The user achieves this by first implementing a listener for the caching:

Note: This example is for illustrative purposes only. There are of course
many other ways to achieve this.


### Declaring a Listener
First, define the listener in their app's `tests.listeners.py` file:

```python
post_reads_per_date_cache = defaultdict(dict)  # dummy cache for illustrative purposes only

@listen('post_reads_per_date')
def post_reads_per_date(
        *,
        post_id: int,
        date: datetime.date,
):
    print(f'Processing post_reads_per_date with args {post_id}, {date}')
    print(f'Cache before: {post_reads_per_date_cache}')
    current_count = post_reads_per_date_cache[date].get(post_id, 0)
    post_reads_per_date_cache[date][post_id] = current_count + 1
    print(f'Cache after: {post_reads_per_date_cache}')
```

The user must also ensure that this `listeners` module is imported into
that app's config class (similar to signals):
```python
class TestsConfig(AppConfig):
    name = 'tests'

    def ready(self):
        import tests.listeners
```

#### Registering listeners
When the project is loaded, the `listen` decorator is called. This
executes this piece of logic:
```python
CustomPayloadChannel.register(callback, channel_name)
```
This creates an instance of CustomPayloadChannel and adds it to a global
registry of "channels".

##### Channels
As in the postgres listen/notify protocol, messages are sent and received
via named channels. The objects defined in channels.py are python abstractions
of these channels. Instances of these classes have the following responsibilities:

- Define an appropriate channel name if one has not been supplied.
    - Undecided on how to best generate the name - see comments in _create_name.
    - This is why in the examples I just define the names manually.
- Listen to notifications on the channel matching their name.
    - See the `listen` method
- Deserialize notifications appropriately for the stored callback (the one
  appearing under the `listen` decorator).
    - I would really like the user to be able to notify the above channel with
      the same payload as is accepted by the `post_reads_per_date` callback.
    - I also want the callback to be able to accept a reasonable variety of different
      python objects.
    - So e.g. like `notify('post_reads_per_date', post_id=pk, date=datetime.date.today())`
    - This means we need a way to easily serialize and then deserialize these arguments
      back into python objects.
    - The obvious choice for this is would be to use `pickle` as the serialization method. This
      however did not work easily as the byte string pickling produced was not accepted by the
      `pg_notify` function. Some sort of replace on the bad characters might let it, but that
      felt a bit hacky.
    - Instead, I've gone with JSON serialization. In order to be able to correctly deserialize
      back to the same object types from a purely JSON payload, I have insisted that the
      user define type annotations on their callback. These type annotations are then used
      to deserialize the JSON payload back to the original python object types, thus allowing
      the user to write callbacks which use these object types.
    - See CustomPayloadChannel.deserialize for more and also the unit tests which show which kind
      of objects we support.
    - Just now I insist that the user also uses keyword arguments only to define these listeners - this was just
      because it made it a bit easier to deserialize when compared to using non-keyword args. This shouldn't
      be a big deal to drop this requirement though.
    - Whilst I personally think this idea is kind of cool, I also feel like it might be overly complicating
      it/potentially re-inventing the wheel? Probably a point we'll need to discuss.
- Execute the callback.
    - This is achieved in `listen` method after correct deserialization.


### Adding the `notify`
Next, the user adds a `fetch` method to `Post` which manually triggers the
above listener (and of course this `fetch` method would then be plugged in to
any API code which performs GET to a post/{id} endpoint):
```python
from pgpubsub.notify import notify
class Post(models.Model):
    ...
    @classmethod
    def fetch(cls, pk):
        post = cls.objects.get(pk=pk)
        notify('post_reads_per_date', post_id=pk, date=datetime.date.today())
        return post
```

### Starting the Listener
The user should start a new python process and make use of the
`listen` management command as follows:
```python
./manage.py listen --channel 'post_reads_per_date'
```
The code for the management command is straightforward and can be seen in
`pgpubsub.management.commands.py`.
An open question remains as to how the user would listen to a channel
whose name had been automatically generated.

### Notifying the post_reads_per_date listener
In another process, fetch a `Post`:
```python
>>> from core.models import *
>>> Post.fetch(12)
{"kwargs": {"post_id": 12, "date": "2022-01-24"}}
<Post: Post object (12)>
```
We can now see logged to the listener process that we've updated the cache:
```python
Processing post_reads_per_date with args 12, 2022-01-24
Cache before: defaultdict(<class 'dict'>, {})
Cache after: defaultdict(<class 'dict'>, {datetime.date(2022, 1, 24): {12: 1}})
```


## Listening to notifications from triggers
Here the user wishes to ensure that whenever an `Author` object is created, a corresponding
`Post` object is created which references the newly created `Author`.

### Declaring a listener
As before, the user declares the listener in their
apps `listeners.py` file.
We can make use of the high-level `pgpubsub.listen.post_insert_listen` decorator here.
```python
@post_insert_listen(channel_name='author_insert', model=Author)
def create_first_post_for_author(trigger_payload: TriggerPayload):
    new_author = trigger_payload.new
    print(f'Creating first post for {new_author.name}')
    Post.objects.create(
        author_id=new_author.pk,
        content='Welcome! This is your first post',
        date=datetime.date.today(),
    )
```
This does two things: registers a listener  and installs
a trigger.

#### Registering the listener
This is very similar to the above example. When the project is loaded,
the `post_insert_listen` decorator is called. This
executes this piece of logic:
```python
TriggerPayloadChannel.register(callback, channel_name)
```
The `TriggerPayloadChannel` is a channel object as described in the previous
example. The only difference between this subclass and the `CustomPayloadChannel`
channel subclass used earlier is the deserialization logic:
- As explained,
  `CustomPayloadChannel` is used to deserialize to match the signature of a custom
  callback,
- `TriggerPayloadChannel` is used to deserialize the payload which comes
  from an notification which is the result of a trigger. These notifications
  are of course invoked at the SQL level, so the user does not directly
  control what they look like. This is why we insist that any "trigger listener"
  (like `create_first_post_for_author`) above has the a signature of taking
  one argument of type `TriggerPayload`. It is thus the responsibility
  of `TriggerPayloadChannel` to deserialize the trigger notification payload
  to a `TriggerPayload` instance (which then has access to `old` and `new` objects).

#### Installing the trigger

The `post_insert_listen` decorator instantiates `Notify` object
as follows
```python
def post_insert_listen(model, channel_name=None):
    return trigger_listen(
        model,
        trigger=Notify(
            name=channel_name,
            when=pgtrigger.After,
            operation=pgtrigger.Insert,
        ),
        channel_name=channel_name,
    )
```
where `Notify` is a subclass of `pgtrigger.Trigger.
This is then installed in `trigger_listen` function:
```python
trigger.install(model)
```
I'm unsure if this is the best practice for installing
triggers programatically.

The `Notify` trigger itself does as we would expect - builds
some JSON from the OLD and NEW rows and then notifies the channel.
Note that we currently set the `name` attribute of the `Notify`
instance as the channel name. I'm undecided if this is the optimal
approach.

### Starting  the listener
Same as before:
```python
./manage.py listen --channel 'author_insert'
```
We then invoke the trigger in one process:
```python
>>> Author.objects.create(name='Paul')
<Author: Author object (48)>
```
Notice that the listening process logged that a notification was received:
```python
Timeout
Timeout
Creating first post for Paul
Timeout
Timeout
```
and that the Post was successfully created in the listening process:
```python
>>> p = Post.objects.last()
>>> p.author.name, p.content
('Paul', 'Welcome! This is your first post')
```


