# Tyche Engine Spec Design
## Definition of the Job
The smallest unit the mesasge queue handle is a 'job', which has at least these attributes:
- type: broadcast|callback
- sender: the specific id of the sender module
- handler: the name of the handler which can handle the job
- wait-timeout: this indicates the maximum time of a job can stay waiting in the queue, and the engine will return an error to the sender if this timeout is reached, then persist the job detail to a file
- run-timeout: this is only mandatory for callback job, indicating the maximum time of running in the handler
- param: the job parameters, this is optional

## Definition of the module
A module is the basic unit of a service endpoint of the system. A module is a single process which can be coded by differnt languages as long as it following the tyche message protocol, it can communicate with other tyche modules via tyche engine.

A module can be running in the same machine of the tyche engine, or running in a different physical node and connects to the engine via internet or other ways of communication.

A module has at least these attributes:
- family name: shows which type of module it is
- module id: the unique module id which is given by tyche engine, as the identifier if the engine needs to find a specific module instance
- admin handlers: handlers expose to the tyche engine to handle the lifecycle of the module instance, including health check, availability check and other commands like respawning and decommision
- handlers: the actual job handlers this module has. The module will hold a dictionary indicating what kinds of job a handler will handle, and a job buffer queue indicating the maximum pending job each handler can have

## Definition of the engine
The engine is basically a job router: it receives registration requests from modules, spawing/subscribing corresponding message queues based on the handler information, and routing jobs to handlers based on the previous registrations.

The engine manages three attributes:
- lifecycle of modules: register, health/availability check, decomission;
- lifecycle of message queue: spawning, health, especially capacity management;
- lifecycle of jobs: routing, waiting, ordering, delivering with promise-to-deliver or try-to-deliver policy;

## Lifecycle management

### 1. Lifecycle of the jobs
The tyche engine need to handle the lifecycle of the job: 

#### Broadcast job
If the job is a broadcast job, the engine does not guarantee if the job is delivered to all subscribers(try-to-deliver policy), however, it guarantees the job is broadcasted by subscribers only once.

If the broadcasted job reaches its waiting timeout, it will be poped out from the message queue and persisted in the file.

#### Callback job
If the job is a callback job, the engine guarantees the job is delivered to an available subscriber(promise-to-deliver), and guarantees the job is done with a return value. The engine must deliver the job to another available handler if the previous handler is timed out.

If the callback job reaches its waiting timeout, it will be poped out from the message queue and persisted in the file.

### 2. Lifecycle of the message queue
The tyche engine will create a message queue when:
- the tyche engine start up, it will only creates a heartbeat message queue and an admin message queue
- when a module registers to the engine, it will automatically subscribing the heartbeat mq, and admin message queue with the corresponding handlers, and the registration request will have to tell the engine about the events and their handlers of the module. The engine will check if the events have message queues, and spawn them if not there, or subscibe to them if they are already there.
- the engine will periodically manage its message queue, checking their capacities

### 3. Lifecycle of the module
When spawing the module, it will read its configuration yaml file and register to the tyche engine configured.

The module will proactively sending heartbeat information to the tyche engine, including the heartbeat event, and availability of the module to each message queue it registers to. The availability is defined as:
- if the buffer queue of the handler still have room for a new job, then this handler of the module is available
- if the buffer queue of the handler is full, then this handler of the module is not available

The tyche engine will dispatching jobs based on the heartbeats of the modules.



