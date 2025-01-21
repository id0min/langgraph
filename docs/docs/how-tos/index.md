---
title: How-to Guides
description: How to accomplish common tasks in LangGraph
---

# How-to Guides

Here you’ll find answers to “How do I...?” types of questions. These guides are **goal-oriented** and concrete; they're meant to help you complete a specific task. For conceptual explanations see the [Conceptual guide](../concepts/index.md). For end-to-end walk-throughs see [Tutorials](../tutorials/index.md). For comprehensive descriptions of every class and function see the [API Reference](../reference/index.md).

## LangGraph

### Controllability

LangGraph provides [low level building primitives](../concepts/low_level.md) that give you control over how you build and execute the graph.

??? "How to create branches for parallel execution"
    Full Example: [How to create branches for parallel execution](branching.ipynb)

    LangGraph enables parallel execution of nodes through fan-out and fan-in mechanisms, enhancing graph performance. By defining a state with a reducer function, you can manage how data is aggregated across parallel branches. Here's a concise example demonstrating this setup:

    ```python
    import operator
    from typing import Annotated, Any
    from typing_extensions import TypedDict
    from langgraph.graph import StateGraph, START, END

    class State(TypedDict):
        # The operator.add reducer function appends to the list
        aggregate: Annotated[list, operator.add]

    class ReturnNodeValue:
        def __init__(self, node_secret: str):
            self._value = node_secret

        def __call__(self, state: State) -> Any:
            print(f"Adding {self._value} to {state['aggregate']}")
            return {"aggregate": [self._value]}

    builder = StateGraph(State)
    builder.add_node("a", ReturnNodeValue("I'm A"))
    builder.add_edge(START, "a")
    builder.add_node("b", ReturnNodeValue("I'm B"))
    builder.add_node("c", ReturnNodeValue("I'm C"))
    builder.add_node("d", ReturnNodeValue("I'm D"))
    builder.add_edge("a", ["b", "c"])  # Fan-out to B and C
    builder.add_edge(["b", "c"], "d")  # Fan-in to D
    builder.add_edge("d", END)
    graph = builder.compile()

    # Execute the graph
    graph.invoke({"aggregate": []})
    ```

    In this setup, the graph fans out from node "a" to nodes "b" and "c", then fans in to node "d". The `aggregate` list in the state accumulates values from each node, demonstrating parallel execution and data aggregation.  


??? "How to create map-reduce branches for parallel execution"

    Full Example: [How to create map-reduce branches for parallel execution](map-reduce.ipynb)

    Use the Send API to split your data or tasks into separate branches and process each in parallel, then combine the outputs with a “reduce” step. This lets you dynamically scale the number of parallel tasks without manually wiring each node.

    ```python
    from langgraph.types import Send

    def continue_to_jokes(state):
        # Distribute jokes generation for each subject in parallel
        return [Send("generate_joke", {"subject": s}) for s in state["subjects"]]
    ```

??? "How to control graph recursion limit"

    Full Example: [How to control graph recursion limit](recursion-limit.ipynb)

    Use the [recursion_limit](../concepts/low_level.md#recursion-limit) parameter in your graph’s invoke method to control how many supersteps are allowed before raising a GraphRecursionError. This guards against infinite loops and excessive computation time.

    ```python
    from langgraph.errors import GraphRecursionError

    try:
        # The recursion_limit sets the max number of supersteps
        # StateGraph, START, and END are relevant langgraph primitives.
        graph.invoke({"aggregate": []}, {"recursion_limit": 4})
    except GraphRecursionError:
        print("Recursion limit exceeded!")
    ```

??? "How to combine control flow and state updates with Command"

    Full Example: [How to combine control flow and state updates with Command](command.ipynb)

    Use a [Command][langgraph.types.Command] return type in a node function to simultaneously update the graph’s state and conditionally decide the next node in the graph. Combining both operations in one step removes the need for separate conditional edges.

    ```python
    from typing_extensions import Literal
    from langgraph.types import Command

    def my_node(state: dict) -> Command[Literal["other_node"]]:
        return Command(
            update={"foo": "bar"},   # state update
            goto="other_node"       # control flow
        )
    ```


### Persistence

[LangGraph Persistence](../concepts/persistence.md) makes it easy to persist state across graph runs (**thread-level** persistence) and across threads (**cross-thread** persistence).

These how-to guides show how to enable persistence:

??? "How to add thread-level persistence to graphs"
    Full Example: [How to add thread-level persistence to graphs](persistence.ipynb)

    Use the MemorySaver checkpointer when compiling your StateGraph to store conversation data across interactions. By specifying a thread_id, you can maintain or reset memory for each conversation thread as needed. This preserves context between messages while still allowing fresh starts.

    ```python
    from langgraph.checkpoint.memory import MemorySaver

    memory = MemorySaver()
    graph = graph_builder.compile(checkpointer=memory)
    ```

??? "How to add thread-level persistence to **subgraphs**"
    Full Example: [How to add thread-level persistence to **subgraphs**](subgraph-persistence.ipynb)

    Pass a single checkpointer (e.g., MemorySaver) when compiling the parent graph, and LangGraph automatically propagates it to any child subgraphs. This avoids passing a checkpointer during subgraph compilation and ensures each thread’s state is captured at every step. 

??? "How to add **cross-thread** persistence to graphs"
    Full Example: [How to add **cross-thread** persistence to graphs](cross-thread-persistence.ipynb)

    Use the [**Store**][langgraph.store.base.BaseStore] API to share state across conversational threads.
    Use a shared Store (e.g., InMemoryStore) to persist user data across different threads. Namespaces keep data for each user separate, and the graph's nodes can retrieve or store memories by referencing the store and user_id. This example demonstrates how to compile a StateGraph with MemorySaver and cross-thread persistence enabled.

    ```python
    from langgraph.store.memory import InMemoryStore
    from langgraph.graph import StateGraph, MessagesState, START
    from langgraph.checkpoint.memory import MemorySaver

    # Initialize a store to hold data across threads
    store = InMemoryStore()

    def my_node(state, config, *, store):
        # Use store to retrieve or store data as needed
        user_id = config["configurable"]["user_id"]
        namespace = ("memories", user_id)
        # For example, store.put(namespace, "key", {"data": "Some info"})
        return state

    builder = StateGraph(MessagesState)
    builder.add_node("my_node", my_node)
    builder.add_edge(START, "my_node")

    # Pass the store when compiling, along with a checkpointer
    graph = builder.compile(checkpointer=MemorySaver(), store=store)
    ```

During development, you will often be using the [MemorySaver][langgraph.checkpoint.memory.MemorySaver] checkpointer. For production use, you will want to persist the data to a database. These how-to guides show how to use different databases for persistence:

??? "How to use Postgres checkpointer for persistence"
    Full Example: [How to use Postgres checkpointer for persistence](persistence_postgres.ipynb)

    Use PostgresSaver or its async variant (AsyncPostgresSaver) from langgraph.checkpoint.postgres to persist conversation or graph states in a PostgreSQL database, enabling your agents or graphs to retain context between runs. Just provide a psycopg connection/pool or a conn string, call setup() once, and pass the checkpointer when compiling (or creating) your StateGraph or agent.

    ```python
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.prebuilt import create_react_agent
    from psycopg import Connection

    DB_URI = "postgresql://user:password@host:port/db"

    with Connection.connect(DB_URI, autocommit=True) as conn:
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()  # Creates necessary tables if not already present
        graph = create_react_agent(model=..., tools=..., checkpointer=checkpointer)
        result = graph.invoke({"messages": [("human", "Hello!")]}, config={"configurable": {"thread_id": "example"}})
    ```

??? "How to use MongoDB checkpointer for persistence"
    Full Example: [How to use MongoDB checkpointer for persistence](persistence_mongodb.ipynb)

    Use the MongoDB checkpointer (MongoDBSaver) from langgraph-checkpoint-mongodb to store and retrieve your graph's state so you can persist interactions across multiple runs. Simply pass the checkpointer into the create_react_agent (or any compiled graph) to automatically handle saving and loading state from your MongoDB instance.

    ```python
    from langgraph.checkpoint.mongodb import MongoDBSaver
    from langgraph.prebuilt import create_react_agent
    from langchain_openai import ChatOpenAI

    MONGODB_URI = "mongodb://localhost:27017"
    model = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)
    tools = []  # define your tools here

    with MongoDBSaver.from_conn_string(MONGODB_URI) as checkpointer:
        graph = create_react_agent(model, tools=tools, checkpointer=checkpointer)
        response = graph.invoke({"messages": [("user", "What's the weather in sf?")]})
        print(response)
    ```

??? "How to create a custom checkpointer using Redis"
    Full Example: [How to create a custom checkpointer using Redis](persistence_redis.ipynb)

    A reference implementation of a custom checkpointer using Redis. Adapt this to your own needs.

### Memory

LangGraph makes it easy to manage conversation [memory](../concepts/memory.md) in your graph.

??? "How to manage conversation history"
    Full Example: [How to manage conversation history](memory/manage-conversation-history.ipynb)

    **Trim** or **filter** messages from the conversation history to fit within the chat model's context window size.


??? "How to delete messages"
    Full Example: [How to delete messages](memory/delete-messages.ipynb)

    You can remove messages from a conversation by passing RemoveMessage objects to the state, provided your MessagesState (or similar) is set up with a reducer that processes them. This helps keep the message list concise and maintain model requirements (e.g. not starting with an AI message). Make sure the remaining conversation flow still follows any format rules your model requires.

    ```python
    # Minimal example illustrating message removal:
    from langchain_core.messages import RemoveMessage

    # Suppose 'app' is a compiled StateGraph using a MessagesState reducer
    # and 'config' is your configuration dictionary with a specific thread_id.
    messages = app.get_state(config).values["messages"]
    message_id_to_remove = messages[0].id

    app.update_state(
        config,
        {"messages": RemoveMessage(id=message_id_to_remove)}
    )

    # 'messages[0]' is now deleted from the conversation state.
    ```

??? "How to add summary conversation memory"
    Full Example: [How to add summary conversation memory](memory/add-summary-conversation-history.ipynb)

    Implement a **running summary** of the conversation history to fit within the chat model's context window size.


Cross-thread memory:

??? "How to add long-term memory (cross-thread)"
    Full Example: [How to add long-term memory (cross-thread)](cross-thread-persistence.ipynb)

    Use the [**Store**][langgraph.store.base.BaseStore] API to share state across conversational threads.
    Use a shared Store (e.g., InMemoryStore) to persist user data across different threads. Namespaces keep data for each user separate, and the graph's nodes can retrieve or store memories by referencing the store and user_id. This example demonstrates how to compile a StateGraph with MemorySaver and cross-thread persistence enabled.

    ```python
    from langgraph.store.memory import InMemoryStore
    from langgraph.graph import StateGraph, MessagesState, START
    from langgraph.checkpoint.memory import MemorySaver

    # Initialize a store to hold data across threads
    store = InMemoryStore()

    def my_node(state, config, *, store):
        # Use store to retrieve or store data as needed
        user_id = config["configurable"]["user_id"]
        namespace = ("memories", user_id)
        # For example, store.put(namespace, "key", {"data": "Some info"})
        return state

    builder = StateGraph(MessagesState)
    builder.add_node("my_node", my_node)
    builder.add_edge(START, "my_node")

    # Pass the store when compiling, along with a checkpointer
    graph = builder.compile(checkpointer=MemorySaver(), store=store)
    ```

??? "How to use semantic search for long-term memory"
    Full Example: [How to use semantic search for long-term memory](memory/semantic-search.ipynb)

    Enable semantic search in your agent by providing an index configuration (e.g., embeddings, vector dimensions) 
    when creating an InMemoryStore. Then, simply store entries with store.put(...) and retrieve semantically similar items using store.search(...).

    ```python
    from langchain.embeddings import init_embeddings
    from langgraph.store.memory import InMemoryStore

    # Initialize embeddings and store
    embeddings = init_embeddings("openai:text-embedding-3-small")
    store = InMemoryStore(index={"embed": embeddings, "dims": 1536})

    # Store some items
    store.put(("agent_id", "memories"), "1", {"text": "I love pizza"})

    # Search semantically
    results = store.search(("agent_id", "memories"), "food preferences", limit=1)
    print(results)
    ```

### Human-in-the-loop

[Human-in-the-loop](../concepts/human_in_the_loop.md) functionality allows you to involve humans in the decision-making process of your graph. These how-to guides show how to implement human-in-the-loop workflows in your graph.

Key workflows:

??? "How to wait for user input"
    Full Example: [How to wait for user input](human_in_the_loop/wait-user-input.ipynb)

    Use the **interrupt()** function in a node to pause graph execution until user input is provided, then pass **Command(resume="some input")** to continue. This is especially helpful for clarifying questions in agentic flows or when building human-in-the-loop interactions in LangGraph.

    ```python
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import Command, interrupt

    def ask_feedback(state):
        feedback = interrupt("Please provide feedback:")
        return {"feedback": feedback}

    builder = StateGraph(dict)
    builder.add_node("ask_feedback", ask_feedback)
    builder.add_edge(START, "ask_feedback")
    builder.add_edge("ask_feedback", END)

    graph = builder.compile()

    # Start execution until it interrupts:
    events = list(graph.stream({}, {"thread_id": "1"}))
    # Resume from interruption:
    graph.stream(Command(resume="User's feedback"), {"thread_id": "1"})
    ```

??? "How to review tool calls"
    Full Example: [How to review tool calls](human_in_the_loop/review-tool-calls.ipynb)

    Use the **interrupt()** function to pause execution and gather user input, then use **Command(resume=…)** to decide how to proceed (e.g. approve, edit, or provide feedback). This helps coordinate a human-in-the-loop flow for reviewing tool calls.

    ```python
    from langgraph.types import interrupt, Command

    def human_review_node(state):
        tool_call = state["messages"][-1].tool_calls[-1]
        human_review = interrupt({"question": "Is this correct?", "tool_call": tool_call})
        
        if human_review["action"] == "continue":
            return Command(goto="run_tool")
        elif human_review["action"] == "update":
            # update the call arguments
            ...
            return Command(goto="run_tool", update={"messages": [updated_message]})
        elif human_review["action"] == "feedback":
            # pass feedback back to the LLM
            ...
            return Command(goto="call_llm", update={"messages": [tool_message]})
    ```

Other methods:

??? "How to add static breakpoints"
    Full Example: [How to add static breakpoints](human_in_the_loop/breakpoints.ipynb)

    Use breakpoints to pause your graph at specific steps by including "interrupt_before" in your compiled StateGraph. Then, resume from the last checkpoint (e.g., saved with MemorySaver) by calling the graph again with None. This allows you to insert human approval before sensitive actions.

    ```python
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.memory import MemorySaver

    def step_1(state): print("Step 1")

    # Create and link nodes
    builder = StateGraph()
    builder.add_node("step_1", step_1)
    builder.add_edge(START, "step_1")
    builder.add_edge("step_1", END)

    # Compile with breakpoints
    graph = builder.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["step_1"]
    )

    # Run once to pause at the breakpoint
    thread = {"configurable": {"thread_id": "example"}}
    graph.run({"input": "hello"}, thread)

    # Resume by passing None as input
    graph.run(None, thread)
    ```


??? "How to edit graph state"
    Full Example: [How to edit graph state](human_in_the_loop/edit-graph-state.ipynb)

    Manually update the graph by setting a breakpoint using “interrupt_before” on a specific node, then edit the state with “update_state” before resuming execution. This approach is especially useful when adjusting tool calls midway. Relevant LangGraph primitives: “StateGraph”, “MemorySaver”, and “interrupt_before”.

    ```python
    from langgraph.graph import StateGraph, START, END
    graph = StateGraph()
    thread = {"configurable": {"thread_id": "1"}}

    # After a breakpoint interrupt:
    print("Current state:", graph.get_state(thread).values)
    graph.update_state(thread, {"input": "edited input!"})
    ```

??? "How to add dynamic breakpoints with `NodeInterrupt` (not recommended)"
    Full Example: [How to add dynamic breakpoints with `NodeInterrupt`](human_in_the_loop/dynamic_breakpoints.ipynb)

    **Not recommended**: Use the [`interrupt` function](../concepts/human_in_the_loop.md) instead.

    **Use** the special exception **NodeInterrupt** to raise a dynamic breakpoint within a node whenever certain conditions are met. After the interrupt is raised, you can update the node's state or inputs before resuming the workflow, or even skip the interrupted node entirely.

    ```python
    from langgraph.errors import NodeInterrupt

    def step_2(state: dict) -> dict:
        if len(state['input']) > 5:
            raise NodeInterrupt("Input too long!")  # Dynamic interrupt
        return state
    ```

### Time Travel

[Time travel](../concepts/time-travel.md) allows you to replay past actions in your LangGraph application to explore alternative paths and debug issues. These how-to guides show how to use time travel in your graph.

??? "How to view and update past graph state"
    Full Example: [How to view and update past graph state](human_in_the_loop/time-travel.ipynb)

    Replay and modify past graph states to explore alternative paths and debug issues in your application.

### Streaming

[Streaming](../concepts/streaming.md) is crucial for enhancing the responsiveness of applications built on LLMs. By displaying output progressively, even before a complete response is ready, streaming significantly improves user experience (UX), particularly when dealing with the latency of LLMs.

??? "How to stream full state of your graph"
    Full Example: [How to stream full state of your graph](stream-values.ipynb)  

    Use **stream_mode="values"** to capture the entire state of the graph after each node call. Simply iterate over the chunks to retrieve and process the full output at each step.

    ```python
    inputs = {"messages": [("human", "what's the weather in sf")]}
    for chunk in graph.stream(inputs, stream_mode="values"):
        print(chunk)
    ```

??? "How to stream state updates of your graph"
    Full Example: [How to stream state updates of your graph](stream-updates.ipynb)  

    Use **stream_mode="updates"** to see real-time changes in each node's state as your graph runs. Just configure your graph, provide inputs, and iterate over the streamed updates to handle them on the fly.

    ```python
    inputs = {"messages": [("human", "What's the weather in sf")]}
    for chunk in graph.stream(inputs, stream_mode="updates"):
        print(chunk)
    ```

??? "How to stream custom data"
    Full Example: [How to stream custom data](streaming-content.ipynb)  

    Use [`StreamWriter`][langgraph.types.StreamWriter] to write custom data to the `custom` stream.

    You can stream custom data from a node by calling **.stream/.astream** with stream_mode="custom" to dispatch intermediate outputs or custom events. This lets you surface progress updates or other information to users in real time.

    ```python
    for chunk in app.stream({"messages": [HumanMessage(content="Show me updates")]}, stream_mode="custom"):
        print(chunk)
    ```

??? "How to multiple streaming modes at the same time"
    Full Example: [How to multiple streaming modes the same time](stream-multiple.ipynb)  

    **Configure multiple streaming modes** by passing a list of modes (e.g., ["updates", "debug"]) when calling astream. This lets you observe detailed updates and debug output simultaneously. Below is a minimal example showing how to stream events of different types together:

    ```python
    for event, chunk in graph.stream({"messages": [("human", "What's the weather in sf")]}, stream_mode=["updates", "debug"]):
        print(f"Event type: {event}")
        print("Event data:", chunk)
    ```

Streaming from specific parts of the application:

??? "How to stream from subgraphs"
    Full Example: [How to stream from subgraphs](streaming-subgraphs.ipynb)

    You can **stream subgraphs** by passing the parameter `subgraphs=True` when calling the stream method, which provides updates from both parent and subgraph nodes. This helps you capture intermediate updates within each subgraph.

    ```python
    for namespace, chunk in graph.stream(input_data, stream_mode="updates", subgraphs=True):
        node_name = list(chunk.keys())[0]
        print(namespace, node_name, chunk[node_name])
    ```

??? "How to stream events from within a tool"
    Full Example: [How to stream events from within a tool](streaming-events-from-within-tools.ipynb)

??? "How to stream events from the final node"
    Full Example: [How to stream events from the final node](streaming-from-final-node.ipynb)

    You can stream from the final node by checking the “langgraph_node” field or attaching custom tags to isolate events for that node. This ensures you only receive tokens from the desired model in real time.

    ```python
    from langchain_core.messages import HumanMessage

    inputs = {"messages": [HumanMessage(content="What's the weather in sf?")]}
    for msg, metadata in graph.stream(inputs, stream_mode="messages"):
        if metadata["langgraph_node"] == "final" and msg.content:
            print(msg.content, end="", flush=True)
    ```

Working with chat models:

??? "How to stream LLM tokens"

    Full Example: [How to stream LLM tokens](streaming-tokens.ipynb)

    Use `stream_mode="messages"` to stream tokens from a chat model as they're generated.

??? "How to disable streaming for models that don't support it"
    Full Example: [How to disable streaming for models that don't support it](disable-streaming.ipynb)

    Set **disable_streaming=True** on your chat model to prevent errors when using models that don’t support streaming. This ensures they won’t be called in streaming mode, even when using the astream_events API.

    ```python
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model="o1", # This model doesn't support streaming at the time of writing
        disable_streaming=True
    )
    ```

??? "How to stream LLM tokens without LangChain models"
    Full Example: [How to stream LLM tokens without LangChain models](streaming-tokens-without-langchain.ipynb)  

    Use LangChain's **callback system** to stream tokens from a custom LLM that is not a [LangChain Chat Model](https://python.langchain.com/docs/concepts/chat_models/).

??? "How to stream events from within a tool without LangChain models"
	Full Example: [How to stream events from within a tool without LangChain models](streaming-events-from-within-tools-without-langchain.ipynb)


### Tool Calling

[Tool calling](https://python.langchain.com/docs/concepts/tool_calling/) is a type of chat model API that accepts tool schemas, along with messages, as input and returns invocations of those tools as part of the output message.

??? "How to call tools using ToolNode"
    Full Example: [How to call tools using ToolNode](tool-calling.ipynb)

    Use the prebuilt **ToolNode** to handle sequential or parallel tool calls from AI messages.

    ```python
    from langgraph.prebuilt import ToolNode
    from langchain_core.messages import AIMessage

    def get_weather(location: str):
        return {"weather": "sunny"}

    tool_node = ToolNode([get_weather, get_coolest_cities])
    message_with_tool_call = AIMessage(tool_calls=[{"name": "get_weather","args": {"location": "sf"}}])
    result = tool_node.invoke({"messages": [message_with_tool_call]})
    print(result)
    ```

??? "How to handle tool calling errors"
    Full Example: [How to handle tool calling errors](tool-calling-errors.ipynb)

??? "How to pass runtime values to tools"
    Full Example: [How to pass runtime values to tools](pass-run-time-values-to-tools.ipynb)

    ```python
    from typing import Annotated
    from langchain_core.runnables import RunnableConfig
    from langchain_core.tools import InjectedToolArg
    from langgraph.store.base import BaseStore
    from langgraph.prebuilt import InjectedState, InjectedStore

    async def my_tool(
        some_arg: str,
        another_arg: float,
        config: RunnableConfig,
        store: Annotated[BaseStore, InjectedStore],
        state: Annotated[State, InjectedState],
        messages: Annotated[list, InjectedState("messages")]
    ):
        """Call my_tool to have an impact on the real world.

        Args:
            some_arg: a very important argument
            another_arg: another argument the LLM will provide
        """
        print(some_arg, another_arg, config, store, state, messages)
        return "... some response"
    ```

??? "How to pass config to tools"
    Full Example: [How to pass config to tools](pass-config-to-tools.ipynb)

??? "How to update graph state from tools"

    Full Example: [How to update graph state from tools](update-state-from-tools.ipynb)

    Use a tool that returns a **Command** with an **update** dictionary to store new graph data (e.g., user info) and message history.

    The tool should be executed in a node that can handle the Command return type, such as a **ToolNode** or a custom node that can process the Command.

    ```python
    from langgraph.types import Command
    from langchain_core.tools import tool

    @tool
    def update_state_tool():
        return Command(update={"my_custom_key": "some_value"})
    ```

??? "How to handle large numbers of tools"
    Full Example: [How to handle large numbers of tools](many-tools.ipynb)

    Use a **vector store** to search over tool descriptions and **dynamically select** relevant tools for each query. This helps reduce token usage and potential errors when handling large sets of tools. 

    ```python
    from langchain_core.tools import StructuredTool
    from langchain_core.documents import Document
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_openai import OpenAIEmbeddings

    # 1) Define a few "tools" with descriptions
    tools = [
        StructuredTool.from_function(
            lambda year: f"Info for CompanyA in {year}",
            name="CompanyA",
            description="Fetch data for CompanyA."
        ),
        StructuredTool.from_function(
            lambda year: f"Info for CompanyB in {year}",
            name="CompanyB",
            description="Fetch data for CompanyB."
        )
    ]

    # 2) Add tool descriptions to a vector store
    docs = [Document(page_content=t.description, metadata={"tool_name": t.name}) for t in tools]
    vector_store = InMemoryVectorStore(embedding=OpenAIEmbeddings())
    vector_store.add_documents(docs)

    # 3) Retrieve and bind only relevant tools to your LLM based on a user query
    query = "Tell me about CompanyB in 2022"
    relevant_tools = vector_store.similarity_search(query)
    matched_tool_names = [doc.metadata["tool_name"] for doc in relevant_tools]
    print("Tools selected:", matched_tool_names)  # Dynamically pick from many tools
    ```

### Subgraphs

[Subgraphs](../concepts/low_level.md#subgraphs) allow you to reuse an existing graph from another graph.

??? "How to add and use subgraphs"
    Full Example: [How to add and use subgraphs](subgraph.ipynb)

    Use **subgraphs** to break your system into smaller graphs that can share or transform state. You can either add a subgraph node directly to your parent graph for shared schema keys or define a node function that invokes a compiled subgraph if the schemas differ.

    ```python
    from langgraph.graph import START, StateGraph
    from typing import TypedDict

    # Define a subgraph
    class SubgraphState(TypedDict):
        bar: str

    def sub_node(state: SubgraphState):
        return {"bar": state["bar"] + " subgraph"}

    sub_builder = StateGraph(SubgraphState)
    sub_builder.add_node(sub_node)
    sub_builder.add_edge(START, "sub_node")
    compiled_subgraph = sub_builder.compile()

    # Define parent graph
    class ParentState(TypedDict):
        foo: str

    def parent_node(state: ParentState):
        result = compiled_subgraph.invoke({"bar": state["foo"]})
        return {"foo": result["bar"]}

    builder = StateGraph(ParentState)
    builder.add_node("parent_node", parent_node)
    builder.add_edge(START, "parent_node")
    graph = builder.compile()

    # Execute the parent graph
    print(graph.invoke({"foo": "Hello,"}))
    ```

??? "How to view and update state in subgraphs"
    Full Example: [How to view and update state in subgraphs](subgraphs-manage-state.ipynb)

    **You can pause subgraphs at breakpoints, inspect their state, and update or override node outputs before resuming execution.** 

    This lets you rewind specific parts of the workflow or inject new data without rerunning the entire graph.

    ```python
    state = graph.get_state(config, subgraphs=True)
    graph.update_state(
        state.tasks[0].state.config, 
        {"city": "Tokyo"}, 
        as_node="weather_node"
    )
    for update in graph.stream(None, config=config, subgraphs=True):
        print(update)
    ```

??? "How to transform inputs and outputs of a subgraph"
    Full Example: [How to transform inputs and outputs of a subgraph](subgraph-transform-state.ipynb)

    You can **wrap** subgraph calls in helper functions to **map** parent state keys to subgraph keys and **transform** the subgraph’s output back to the parent. This lets each subgraph maintain its own independent state while still sharing data. 

    ```python
    def transform_and_call_subgraph(parent_state: dict) -> dict:
        # Map parent key to subgraph key
        child_input = {"my_child_key": parent_state["my_key"]}
        # Invoke subgraph
        child_output = child_graph.invoke(child_input)
        # Map subgraph key back to parent
        return {"my_key": child_output["my_child_key"]}
    ```
### Multi-Agent

[Multi-agent systems](../concepts/multi_agent.md) are useful to break down complex LLM applications into multiple agents, each responsible for a different part of the application. These how-to guides show how to implement multi-agent systems in LangGraph:

??? "How to implement handoffs between agents"
    Full Example: [How to implement handoffs between agents](agent-handoffs.ipynb)

    Use a **Command** object or a specialized "handoff tool" that returns a Command, with goto specifying the next agent and update for transferring state. This approach allows agents to route requests or share context seamlessly.

    ```python
    from langgraph.types import Command

    def agent(state):
        # Decide on the next agent
        next_agent = "other_agent"
        return Command(goto=next_agent, update={"key": "value"})
    ```

??? "How to build a multi-agent network"
    Full Example: [How to build a multi-agent network](multi-agent-network.ipynb)



??? "How to add multi-turn conversation in a multi-agent application"
    Full Example: [How to add multi-turn conversation in a multi-agent application](multi-agent-multi-turn-convo.ipynb)

    **Use an interrupt node to gather user input, append it to the conversation state, and reroute to the active agent.** The agent then processes the new message to produce a response or hand off to another agent as needed.

    ```python
    def human_node(state):
        user_input = interrupt(value="Provide your input:")
        active_agent = ...  # Determine the active agent
        return Command(
            update={"messages": [{"role": "human", "content": user_input}]},
            goto=active_agent
        )
    ```

See the [multi-agent tutorials](../tutorials/index.md#multi-agent-systems) for implementations of other multi-agent architectures.

### State Management

??? "How to use Pydantic model as state"
    Full Example: [How to use Pydantic model as state](state-model.ipynb)

    Use a Pydantic BaseModel to define your graph’s state and automatically validate node inputs. Any mismatch in types or invalid data triggers a pydantic validation error at runtime.

    ```python
    from pydantic import BaseModel
    from langgraph.graph import StateGraph, START, END

    class MyState(BaseModel):
        a: str

    def node(state: MyState):
        return {"a": "goodbye"}

    builder = StateGraph(MyState)
    builder.add_node(node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)
    graph = builder.compile()

    # Valid input
    print(graph.invoke({"a": "hello"}))
    ```

??? "How to define input/output schema for your graph"
    Full Example: [How to define input/output schema for your graph](input_output_schema.ipynb)

    You can **define** separate typed dictionaries for your input and output schemas to ensure only relevant fields are included in the final output. Simply specify these schemas when creating the StateGraph and return the necessary data from each node.

    ```python
    from langgraph.graph import StateGraph, START, END
    from typing_extensions import TypedDict

    class InputState(TypedDict):
        question: str

    class OutputState(TypedDict):
        answer: str

    def answer_node(state: InputState):
        return {"answer": f"Your question was: {state['question']}"}

    builder = StateGraph(input=InputState, output=OutputState)
    builder.add_node(answer_node)
    builder.add_edge(START, "answer_node")
    builder.add_edge("answer_node", END)
    graph = builder.compile()

    print(graph.invoke({"question": "Hi"}))  # Prints {'answer': 'Your question was: Hi'}
    ```

??? "How to pass private state between nodes inside the graph"
    Full Example: [How to pass private state between nodes inside the graph](pass_private_state.ipynb)

    You can define separate schemas for private and public data, then configure your nodes so only the intended steps receive the private fields, while the rest of the nodes access only the public state. This way, internal information is passed between specific nodes and kept out of the final schema.

    ```python
    from langgraph.graph import StateGraph, START, END
    from typing_extensions import TypedDict

    class OverallState(TypedDict):
        a: str

    class Node1Output(TypedDict):
        private_data: str

    def node_1(state: OverallState) -> Node1Output:
        return {"private_data": "secret_value"}

    def node_2(state: Node1Output) -> OverallState:
        return {"a": "public_value"}

    def node_3(state: OverallState) -> OverallState:
        return {"a": "final_value"}

    builder = StateGraph(OverallState)
    builder.add_node(node_1)
    builder.add_node(node_2)
    builder.add_node(node_3)
    builder.add_edge(START, "node_1")
    builder.add_edge("node_1", "node_2")
    builder.add_edge("node_2", "node_3")
    builder.add_edge("node_3", END)
    graph = builder.compile()

    print(graph.invoke({"a": "initial_value"}))
    ```

### Other

??? "How to run graph asynchronously"
    Full Example: [How to run graph asynchronously](async.ipynb)

    Define nodes with **async def** and use **await** for asynchronous calls. Then compile your graph with a StateGraph and call it using app.ainvoke(...) to run the graph concurrently.

    ```python
    async def call_model(state):
        response = await model.ainvoke(state["messages"])
        return {"messages": [response]}

    result = await app.ainvoke({"messages": [HumanMessage(content="Hello")]})
    ```

??? "How to visualize your graph"
    Full Example: [How to visualize your graph](visualization.ipynb)

    You can visualize your Graph by converting it to Mermaid syntax or generating a PNG. Below is a minimal example to create and draw a Graph.

    ```python
    from IPython import display
    from langgraph.graph import StateGraph, START, END

    builder = StateGraph(dict)
    builder.add_node("my_node", lambda state: {"messages": ["Hello from my_node"]})
    builder.add_edge(START, "my_node")
    builder.add_edge("my_node", END)
    graph = builder.compile()

    display.Image(graph.get_graph().draw_mermaid_png())
    ```

??? "How to add runtime configuration to your graph"
    Full Example: [How to add runtime configuration to your graph](configuration.ipynb)

    Configure your graph at runtime by passing parameters under the "configurable" key in a config object. This way, you can dynamically choose which model to use or add extra settings without altering the tracked state.

    ```python
    config = {"configurable": {"model": "openai"}}
    graph.invoke({"messages": [HumanMessage(content="Hello!")]}, config=config)
    ```

??? "How to add node retries"
    Full Example: [How to add node retries](node-retries.ipynb)

    Use the “retry” parameter in add_node() to configure how many times a node is retried, intervals between attempts, and which exceptions trigger a retry. This can handle errors from external calls such as APIs or databases.

    ```python
    from langgraph.pregel import RetryPolicy

    builder.add_node(
        "my_node",
        my_func,
        retry=RetryPolicy(max_attempts=3, backoff_factor=2.0)
    )
    ```
??? "How to force function calling agent to structure output"
    Full Example: [How to force function calling agent to structure output](react-agent-structured-output.ipynb)

    Use a single LLM plus a “response tool” or call a second LLM that enforces structured output. Both approaches ensure consistent, parseable results. This makes it easier to integrate the agent’s answer into downstream workflows.

??? "How to pass custom LangSmith run ID for graph runs"
    Full Example: [How to pass custom LangSmith run ID for graph runs](run-id-langsmith.ipynb)

    **Add a custom** `run_id`, `tags`, and `metadata` to your LangGraph `RunnableConfig` to organize and filter your runs in LangSmith. Initialize these fields before calling methods like `.stream()` or `.invoke()` to keep your traces tidy.

    ```python
    import uuid

    config = {
        "run_id": str(uuid.uuid4()),
        "tags": ["custom_tag"],
        "metadata": {"key": "value"},
    }

    graph.invoke("Hello, world!", config)
    ```

??? "How to return state before hitting recursion limit"
    Full Example: [How to return state before hitting recursion limit](return-when-recursion-limit-hits.ipynb)

    Simply track the remaining steps in your state and end the graph before the recursion limit triggers an error, returning the last state. Use a special “RemainingSteps” annotation, check if it’s near zero, and terminate gracefully.

    ```python
    from typing_extensions import TypedDict
    from typing import Annotated
    from langgraph.graph import StateGraph, START, END
    from langgraph.managed.is_last_step import RemainingSteps

    class State(TypedDict):
        value: str
        remaining_steps: RemainingSteps

    def router(state: State):
        if state["remaining_steps"] <= 2:
            return END
        return "action"

    def action_node(state: State):
        return {}

    flow = StateGraph(State)
    flow.add_node("action", action_node)
    flow.add_edge(START, "action")
    flow.add_conditional_edges("action", router, ["action", END])

    app = flow.compile()
    result = app.invoke({"value": "test"})
    print(result)
    ```

??? "How to integrate LangGraph with AutoGen, CrewAI, and other frameworks"
    Full Example: [How to integrate LangGraph with AutoGen, CrewAI, and other frameworks](autogen-integration.ipynb)

    LangGraph can integrate with frameworks like **AutoGen** or **CrewAI** by wrapping those frameworks in LangGraph nodes. Then, define a multi-agent system that references both the external agent node and local agents. Finally, run the orchestrated graph for coordinated multi-agent interactions.

### Prebuilt ReAct Agent

The LangGraph [prebuilt ReAct agent](../reference/prebuilt.md#langgraph.prebuilt.chat_agent_executor.create_react_agent) is a pre-built implementation of a [tool calling agent](../concepts/agentic_concepts.md#tool-calling-agent).

One of the big benefits of LangGraph is that you can easily create your own agent architectures. So while it's fine to start here to build an agent quickly, we would strongly recommend learning how to build your own agent so that you can take full advantage of LangGraph.

These guides show how to use the prebuilt ReAct agent:

??? "How to create a ReAct agent"
    Full Example: [How to create a ReAct agent](create-react-agent.ipynb)

    Use the prebuilt create_react_agent() function with a chat model and tools to handle user requests. The agent decides whether to call a tool or return an answer based on the conversation. Provide your LLM and any needed tools, and the agent will manage the rest.

    ```python
    from langgraph.prebuilt import create_react_agent

    model = ... # Initialize your LLM
    tools = [...] # Initialize your tools

    agent = create_react_agent(model, tools=tools)
    result = agent({"messages": [("user", "What is the weather in sf?")]})
    print(result)
    ```

??? "How to add memory to a ReAct agent"
    Full Example: [How to add memory to a ReAct agent](create-react-agent-memory.ipynb)

    Add a **checkpointer** (like MemorySaver) to the create_react_agent function to enable memory in your ReAct agent. This way, the agent retains conversation history across calls for more dynamic interactions.

    ```python
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.prebuilt import create_react_agent

    memory = MemorySaver()
    graph = create_react_agent(model, tools=tools, checkpointer=memory)
    ```

??? "How to add a custom system prompt to a ReAct agent"
    Full Example: [How to add a custom system prompt to a ReAct agent](create-react-agent-system-prompt.ipynb)

    Add a custom system prompt to the prebuilt ReAct agent by passing **your desired instructions** to the state_modifier parameter. This modifies the agent’s system prompt and guides its responses.

    ```python
    from langgraph.prebuilt import create_react_agent

    model = ... # Initialize your LLM

    prompt = "Respond in Italian"
    agent = create_react_agent(model, tools=[], state_modifier=prompt)
    ```

??? "How to add human-in-the-loop processes to a ReAct agent"
    Full Example: [How to add human-in-the-loop processes to a ReAct agent](create-react-agent-hitl.ipynb)

    **You can add a human review step by passing** `interrupt_before=["tools"]` **to the ReAct agent and using a checkpointer to pause execution whenever a tool call is about to happen. This allows you to inspect or modify the agent’s proposed tool calls before continuing.**

    ```python
    from langgraph.prebuilt import create_react_agent
    from langgraph.checkpoint.memory import MemorySaver

    model = ... # Initialize your LLM
    memory = MemorySaver() # Initialize your checkpointer

    graph = create_react_agent(
        model,
        tools=[],  # Add your tools here
        interrupt_before=["tools"],
        checkpointer=memory
    )
    ```

??? "How to create prebuilt ReAct agent from scratch"
    Full Example: [How to create prebuilt ReAct agent from scratch](react-agent-from-scratch.ipynb)

    **Define a custom ReAct agent** by specifying a basic agent state, linking a chat model to relevant tools, and building a node-based workflow in LangGraph. Then pass user messages to the compiled graph to handle tool usage and respond.

    ```python
    from langgraph.graph import StateGraph, END

    # Define your state class, model, tool nodes, and callback functions here (AgentState, call_model, tool_node, should_continue)

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", should_continue, {"continue": "tools", "end": END})
    workflow.add_edge("tools", "agent")
    graph = workflow.compile()

    response = graph.run({"messages": [("user", "What is the weather in SF?")]})
    print(response["messages"][-1].content)
    ```

??? "How to add semantic search for long-term memory to a ReAct agent"
    Full Example: [How to add semantic search for long-term memory to a ReAct agent](memory/semantic-search.ipynb#using-in-create-react-agent)

    **Enable semantic search** by providing an embeddings-based index config when creating your memory store. Store data with `.put(...)` and retrieve relevant entries via `.search(...)`, letting your agent recall context from stored information seamlessly.

    ```python
    from langchain.embeddings import init_embeddings
    from langgraph.store.memory import InMemoryStore

    embeddings = init_embeddings("openai:text-embedding-3-small")
    store = InMemoryStore(index={"embed": embeddings, "dims": 1536})

    store.put(("user_123","memories"), "1", {"text": "I love pizza"})
    results = store.search(("user_123","memories"), query="favorite food", limit=1)
    print(results)
    ```

## LangGraph Platform

This section includes how-to guides for LangGraph Platform.

LangGraph Platform is a commercial solution for deploying agentic applications in production, built on the open-source LangGraph framework.

The LangGraph Platform offers a few different deployment options described in the [deployment options guide](../concepts/deployment_options.md).

!!! tip

    * LangGraph is an MIT-licensed open-source library, which we are committed to maintaining and growing for the community.
    * You can always deploy LangGraph applications on your own infrastructure using the open-source LangGraph project without using LangGraph Platform.

### Application Structure

Learn how to set up your app for deployment to LangGraph Platform:

??? "How to set up app for deployment"

    *  [How to set up app for deployment (requirements.txt)](../cloud/deployment/setup.md)
    *  [How to set up app for deployment (pyproject.toml)](../cloud/deployment/setup_pyproject.md)
    *  [How to set up app for deployment (JavaScript)](../cloud/deployment/setup_javascript.md)

    Specify your **dependencies** (e.g., requirements.txt) and **environment variables** (e.g., .env), then define your graphs in a Python module. Finally, create a **langgraph.json** to reference your compiled graphs for deployment.

    ```python
    from typing import TypedDict
    from langgraph.graph import StateGraph, START, END

    class State(TypedDict):
        foo: str

    def example_node(state):
        return {
            "foo": "Hello from LangGraph!"
        }

    graph = (
        StateGraph(State)
        .add_node("say_hello", example_node)
        .add_edge(START, "say_hello")
        .add_edge("say_hello", END)
        .compile()
    )
    ```


??? "How to customize Dockerfile"

    Full Example: [How to customize Dockerfile](../cloud/deployment/custom_docker.md)

    Modify langgraph.json to include custom Dockerfile lines for your app. This lets you install additional dependencies or configure your environment as needed.

    ```json
    {
        "dependencies": ["."],
        "graphs": {
            "openai_agent": "./openai_agent.py:agent",
        },
        "env": "./.env",
        "dockerfile_lines": [
            "RUN apt-get update && apt-get install -y libjpeg-dev zlib1g-dev libpng-dev",
            "RUN pip install Pillow"
        ]
    }
    ```

??? "How to test locally"

    Full Example: [How to test locally](../cloud/deployment/test_locally.md)

    **Install** the CLI, **run** your server with `langgraph dev`, and **use** a client to test your graph endpoints locally with a valid API key. **Ensure** your environment variables are set or pass them to the client initialization.


??? "How to rebuild graph at runtime"

    Full Example: [How to rebuild graph at runtime](../cloud/deployment/graph_rebuild.md)

    You can define a **function** that returns a compiled graph based on your config, then reference that function in your "langgraph.json" file. This enables you to rebuild your graph for each new run using different parameters.

    ```python
    # Filename: graph.py
    def make_graph(config):
        # Define and compile a graph based on the config
        return compiled_graph
    ```

    In `langgraph.json` reference the function in the "graphs" section:

    ```json
    {
        "dependencies": ["."],
        "graphs": {
            "agent_name": "graph.py:make_graph",
        },
        "env": "./.env"
    }
    ```

    The function can be an `async` function if you need to perform asynchronous operations during graph compilation.

??? "How to use LangGraph Platform to deploy CrewAI, AutoGen, and other frameworks"

    Full Example: [How to use LangGraph Platform to deploy CrewAI, AutoGen, and other frameworks](autogen-langgraph-platform.ipynb)


### Deployment

LangGraph applications can be deployed using LangGraph Cloud, which provides a range of services to help you deploy, manage, and scale your applications.

??? "How to deploy to LangGraph cloud"
	Full Example: [How to deploy to LangGraph cloud](../cloud/deployment/cloud.md)

    Deploy your code from a GitHub repository to LangGraph Cloud via the LangSmith UI, then manage new revisions, environment variables, and logs.


??? "How to deploy to a self-hosted environment"
	Full Example: [How to deploy to a self-hosted environment](./deploy-self-hosted.md)

    Use the LangGraph CLI to build a Docker image for your application, then pass in the required environment variables (e.g., REDIS_URI and DATABASE_URI) to run it. Below is a minimal example:

    ```bash
    pip install -U langgraph-cli
    langgraph build -t my-image
    docker run \
        --env-file .env \
        -p 8123:8000 \
        -e REDIS_URI="foo" \
        -e DATABASE_URI="bar" \
        my-image
    ```

??? "How to interact with the deployment using RemoteGraph"
	Full Example: [How to interact with the deployment using RemoteGraph](./use-remote-graph.md)

    Initialize a RemoteGraph by specifying the graph name and either a URL or a sync client. Then call its invoke() or stream() methods synchronously. Below is a minimal Python snippet:

    ```python
    from langgraph_sdk import get_sync_client
    from langgraph.pregel.remote import RemoteGraph

    url = "<DEPLOYMENT_URL>"
    graph_name = "agent"

    sync_client = get_sync_client(url=url)
    remote_graph = RemoteGraph(graph_name, sync_client=sync_client)

    result = remote_graph.invoke({
        "messages": [{"role": "user", "content": "What's the weather in SF?"}]
    })
    print(result)
    ```

### Authentication & Access Control

- [How to add custom authentication](./auth/custom_auth.md)
- [How to update the security schema of your OpenAPI spec](./auth/openapi_security.md)

### Assistants

[Assistants](../concepts/assistants.md) is a configured instance of a template.

??? "How to configure agents"
	Full Example: [How to configure agents](../cloud/how-tos/configuration_cloud.md)

??? "How to version assistants"
	Full Example: [How to version assistants](../cloud/how-tos/assistant_versioning.md)

    Version your assistant by creating it with a specific config, then use the update endpoint to generate a new version with any additional config changes. You can easily switch between versions as needed.

    ```python
    from langgraph_sdk import get_client

    client = get_client(url="https://your-deployment-url")
    graph_name = "agent"

    # Create an assistant
    assistant = client.assistants.create(
        graph_name,
        config={"configurable": {"model_name": "openai"}},
        name="my_assistant"
    )

    # Create a new version with an updated config
    assistant_v2 = client.assistants.update(
        assistant["assistant_id"],
        config={"configurable": {"model_name": "openai", "system_prompt": "You are a helpful assistant!"}}
    )
    ```

### Threads

??? "How to copy threads"
	Full Example: [How to copy threads](../cloud/how-tos/copy_threads.md)

    Copying a thread lets you preserve the original thread’s history while creating a new thread for independent runs. Create a new thread copy from an existing one, then verify the history matches the original.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    thread = client.threads.create()

    copied_thread = client.threads.copy("<THREAD_ID>")

    original_thread_history = client.threads.get_history("<THREAD_ID>")
    copied_thread_history = client.threads.get_history(copied_thread["thread_id"])
    ```

??? "How to check status of your threads"
	Full Example: [How to check status of your threads](../cloud/how-tos/check_thread_status.md)

    You can query threads to see if they’re idle, interrupted, or busy, and you can also filter by ID or metadata to find specific threads. Below is an example using the synchronous Python client:

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")

    # Find idle threads
    idle_threads = client.threads.search(status="idle", limit=1)
    print(idle_threads)

    # Find a thread by ID
    thread_info = client.threads.get("<THREAD_ID>")
    print(thread_info["status"])
    ```

### Runs

LangGraph Platform supports multiple types of runs besides streaming runs.

??? "How to run an assistant in the background"
	Full Example: [How to run an in the background](../cloud/how-tos/background_run.md)

    Kick off background runs by creating a thread, sending your request, then waiting on the run to finish using "join". Once complete, fetch the final state from the thread for the results.

    ```python
    from langgraph_sdk import get_sync_client

    # Create client (async)
    client = get_sync_client(url="YOUR_DEPLOYMENT_URL")

    # Create a new thread
    thread = client.threads.create()

    # Start a background run
    input_data = {"messages": [{"role": "user", "content": "what's the weather in sf"}]}
    run = client.runs.create(thread["thread_id"], "agent", input=input_data)

    # Wait for the run to finish
    client.runs.join(thread["thread_id"], run["run_id"])

    # Retrieve final result
    final_state = client.threads.get_state(thread["thread_id"])
    print(final_state['values']['messages'][-1]['content'][0]['text'])
    ```

??? "How to run multiple agents in the same thread"
	Full Example: [How to run multiple agents in the same thread](../cloud/how-tos/same-thread.md)

    **Use the same thread ID** to let multiple agents share conversation context. Simply create a thread once, then call each agent on that thread to continue where the previous one left off.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    thread = client.threads.create()

    client.runs.stream(
        thread["thread_id"],
        "FIRST ASSISTANT ID",
        input={"messages": [{"role": "user", "content": "Hello from OpenAI agent"}]},
        stream_mode="updates",
    )

    client.runs.stream(
        thread["thread_id"],
        "DIFFERENT ASSISTANT ID",
        input={"messages": [{"role": "user", "content": "Continuing with default agent"}]},
        stream_mode="updates",
    )
    ```

??? "How to create cron jobs"

    Full Example: [How to create cron jobs](../cloud/how-tos/cron_jobs.md)

    **Cron jobs** allow you to schedule your graph to run on a set timetable (e.g., sending automated emails) rather than waiting for user input. Simply provide a cron expression to define your schedule, and always remember to delete old jobs to avoid excess usage.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="YOUR_DEPLOYMENT_URL")
    assistant_id = "agent"

    # Create a thread (sync version)
    thread = client.threads.create()

    # Schedule a cron job to run daily at 15:27
    cron_job = client.crons.create_for_thread(
        thread["thread_id"],
        assistant_id,
        schedule="27 15 * * *",
        input={"messages": [{"role": "user", "content": "What time is it?"}]}
    )

    # Delete the cron job
    client.crons.delete(cron_job["cron_id"])
    ```

??? "How to create stateless runs"
	Full Example: [How to create stateless runs](../cloud/how-tos/stateless_runs.md)


### Streaming

Streaming the results of your LLM application is vital for ensuring a good user experience, especially when your graph may call multiple models and take a long time to fully complete a run. Read about how to stream values from your graph in these how-to guides:

??? "How to stream values"
	Full Example: [How to stream values](../cloud/how-tos/stream_values.md)

    Use "values" streaming mode to retrieve the entire graph state after each node executes. Provide an input, then iterate over the streaming response for each superstep.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    input_data = {"messages": [{"role": "user", "content": "What's the weather in LA"}]}

    for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id,
        input=input_data,
        stream_mode="values",
    ):
        print(f"Receiving new event of type: {chunk.event}...")
        print(chunk.data)
    ```

??? "How to stream updates"
	Full Example: [How to stream updates](../cloud/how-tos/stream_updates.md)

    You can enable streaming of state updates (rather than the full state) by setting stream_mode="updates". Each chunk of streamed data contains only the new or changed parts of the graph's state after each node runs.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")  # sync version
    assistant_id = "agent"
    thread = client.threads.create()
    input_data = {
        "messages": [
            {
                "role": "user",
                "content": "what's the weather in la"
            }
        ]
    }

    for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id,
        input=input_data,
        stream_mode="updates",
    ):
        print(f"Receiving new event: {chunk.event}")
        print(chunk.data)
    ```

??? "How to stream messages"
	Full Example: [How to stream messages](../cloud/how-tos/stream_messages.md)

    Use "messages-tuple" to receive LLM tokens from nodes in real-time. Create a thread and call runs.stream with stream_mode set to "messages-tuple" to get a tuple containing each token's text and metadata.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"

    thread = client.threads.create()
    print(thread)

    input_data = {"messages": [{"role": "user", "content": "What's the weather in sf"}]}
    config = {"configurable": {"model_name": "openai"}}

    for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id=assistant_id,
        input=input_data,
        config=config,
        stream_mode="messages-tuple"
    ):
        print(f"Receiving new event of type: {chunk.event}...")
        print(chunk.data)
        print()
    ```

??? "How to stream events"
	Full Example: [How to stream events](../cloud/how-tos/stream_events.md)

    Use the events streaming mode to get real-time updates of each event that occurs in your graph. Provide an input to your graph and iterate the returned stream to receive and handle each event as it happens.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": "What's the weather in SF?",
            }
        ]
    }

    for chunk in client.runs.stream(
        thread_id=thread["thread_id"],
        assistant_id=assistant_id,
        input=input_data,
        stream_mode="events",
    ):
        print(f"Receiving new event of type: {chunk.event}...")
        print(chunk.data)
    ```

??? "How to stream in debug mode"
	Full Example: [How to stream in debug mode](../cloud/how-tos/stream_debug.md)

    You can stream debug events from your graph by setting stream_mode="debug", which returns a series of events with details about checkpoints, tasks, and results. These events help you follow each super-step of your graph to spot issues or monitor execution.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": "What's the weather in SF?",
            }
        ]
    }

    for chunk in client.runs.stream(
        thread_id=thread["thread_id"],
        assistant_id=assistant_id,
        input=input_data,
        stream_mode="debug",
    ):
        print(f"Received event: {chunk.event}")
        print(chunk.data)
    ```

??? "How to stream multiple modes"
	Full Example: [How to stream multiple modes](../cloud/how-tos/stream_multiple.md)

    You can enable multiple streaming outputs by passing a list of modes (e.g. ["messages", "events", "debug"]) in the stream_mode parameter. Each mode then emits its own stream events.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    input_data = {
        "messages": [
            {
                "role": "user",
                "content": "What's the weather in SF?",
            }
        ]
    }

    for chunk in client.runs.stream(
        thread_id=thread["thread_id"],
        assistant_id=assistant_id,
        input=input_data,
        stream_mode=["messages", "events", "debug"],
    ):
        print(f"Receiving new event of type: {chunk.event}...")
        print(chunk.data)
    ```

### Human-in-the-loop

When designing complex graphs, relying entirely on the LLM for decision-making can be risky, particularly when it involves tools that interact with files, APIs, or databases. These interactions may lead to unintended data access or modifications, depending on the use case. To mitigate these risks, LangGraph allows you to integrate human-in-the-loop behavior, ensuring your LLM applications operate as intended without undesirable outcomes.

??? "How to add a breakpoint"
	Full Example: [How to add a breakpoint](../cloud/how-tos/human_in_the_loop_breakpoint.md)

    You can add a breakpoint by specifying "interrupt_before" on the relevant node. This pauses execution at that node, letting you resume afterward.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url=<DEPLOYMENT_URL>)
    assistant_id = "agent"
    thread = client.threads.create()

    input_data = {"messages": [{"role": "user", "content": "what's the weather in sf"}]}
    response = client.runs.run(
        thread["thread_id"],
        assistant_id,
        input=input_data,
        interrupt_before=["action"]
    )

    print(response)
    ```

??? "How to wait for user input"
	Full Example: [How to wait for user input](../cloud/how-tos/human_in_the_loop_user_input.md)

    Use a breakpoint before the node where human input is needed, then update the graph state (with as_node) so that execution resumes from that node after adding the user’s response. This approach allows your graph to pause for input and then continue without starting over.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"

    # 1. Create a thread
    thread = client.threads.create()

    # 2. Initial invocation, interrupting before "ask_human" node
    input_data = {"messages": [{"role": "user", "content": "Where are you located?"}]}
    for chunk in client.runs.stream(
        thread["thread_id"], assistant_id, input=input_data,
        stream_mode="updates", interrupt_before=["ask_human"]
    ):
        if chunk.data and chunk.event != "metadata":
            print(chunk.data)

    # 3. Update state with the user's response
    state = client.threads.get_state(thread["thread_id"])
    tool_call_id = state["values"]["messages"][-1]["tool_calls"][0]["id"]
    tool_message = [{"tool_call_id": tool_call_id, "type": "tool", "content": "San Francisco"}]
    client.threads.update_state(
        thread["thread_id"], {"messages": tool_message},
        as_node="ask_human"
    )

    # 4. Continue execution
    for chunk in client.runs.stream(thread["thread_id"], assistant_id, input=None, stream_mode="updates"):
        if chunk.data and chunk.event != "metadata":
            print(chunk.data)
    ```

??? "How to edit graph state"
	Full Example: [How to edit graph state](../cloud/how-tos/human_in_the_loop_edit_state.md)

    To interrupt a graph run before a node, retrieve and modify the relevant portion of the state, and then resume execution, you can invoke your deployed graph with an “interrupt_before” parameter, update the state through the SDK, and continue from the same point.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    # 1. Invoke with interrupt
    for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id,
        input={"messages": [{"role": "user", "content": "search for weather in SF"}]},
        interrupt_before=["action"],
        stream_mode="updates",
    ):
        print(chunk)

    # 2. Update the state
    current_state = client.threads.get_state(thread["thread_id"])
    last_message = current_state["values"]["messages"][-1]
    last_message["tool_calls"][0]["args"] = {"query": "current weather in Sidi Frej"}
    client.threads.update_state(thread["thread_id"], {"messages": last_message})

    # 3. Resume execution
    for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id,
        stream_mode="updates",
    ):
        print(chunk)
    ```

??? "How to replay and branch from prior states"
	Full Example: [How to replay and branch from prior states](../cloud/how-tos/human_in_the_loop_time_travel.md)

    You can revisit previous states by referencing their checkpoint_id to rerun or modify them for alternate paths. This lets you debug or explore different outcomes mid-conversation.

    ```python
    from langgraph_sdk import get_sync_client

    # Connect to your deployed graph
    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    # Get all prior states
    states = client.threads.get_history(thread["thread_id"])
    state_to_replay = states[2]

    # Update the thread to replay from a chosen checkpoint
    updated_config = client.threads.update_state(
        thread["thread_id"],
        {"messages": []},
        checkpoint_id=state_to_replay["checkpoint_id"]
    )

    # Re-run the graph from that checkpoint
    for chunk in client.runs.stream(
        thread["thread_id"],
        assistant_id,
        input=None,
        stream_mode="updates",
        checkpoint_id=updated_config["checkpoint_id"]
    ):
        if chunk.data and chunk.event != "metadata":
            print(chunk.data)
    ```

??? "How to review tool calls"
	Full Example: [How to review tool calls](../cloud/how-tos/human_in_the_loop_review_tool_calls.md)

    Use breakpoints to intercept and review tool calls in a human-in-the-loop process. You can approve, edit, or provide feedback on a tool call by updating the graph state accordingly.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    thread = client.threads.create()

    # Submit user input
    input_data = {"messages": [{"role": "user", "content": "What's the weather in SF?"}]}
    for chunk in client.runs.stream(thread["thread_id"], "agent", input=input_data):
        if chunk["data"] and chunk["event"] != "metadata":
            print(chunk["data"])

    # Tool call is now waiting for review - approve by sending no input
    for chunk in client.runs.stream(thread["thread_id"], "agent", input=None):
        if chunk["data"] and chunk["event"] != "metadata":
            print(chunk["data"])
    ```

### Double-texting

Graph execution can take a while, and sometimes users may change their mind about the input they wanted to send before their original input has finished running. For example, a user might notice a typo in their original request and will edit the prompt and resend it. Deciding what to do in these cases is important for ensuring a smooth user experience and preventing your graphs from behaving in unexpected ways.

??? "How to use the interrupt option"
	Full Example: [How to use the interrupt option](../cloud/how-tos/interrupt_concurrent.md)

    Use **interrupt** to halt the previous run and mark it as “interrupted”, then start a new run without deleting the first one. This keeps the original run data in the database while focusing on the fresh run.

??? "How to use the rollback option"
	Full Example: [How to use the rollback option](../cloud/how-tos/rollback_concurrent.md)

    Use **rollback** to fully remove a previous run from the database before starting a new run. The old run becomes inaccessible once this new run is triggered. Below is a minimal example:

    ```python
    import requests
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"
    thread = client.threads.create()

    rolled_back_run = client.runs.create(
        thread["thread_id"],
        assistant_id,
        input={"messages": [{"role": "user", "content": "What's the weather in SF?"}]},
    )

    run = client.runs.create(
        thread["thread_id"],
        assistant_id,
        input={"messages": [{"role": "user", "content": "What's the weather in NYC?"}]},
        multitask_strategy="rollback",
    )

    client.runs.join(thread["thread_id"], run["run_id"])
    ```

??? "How to use the reject option"
	Full Example: [How to use the reject option](../cloud/how-tos/reject_concurrent.md)

    Use the **"reject"** strategy to block a second concurrent run, causing an error if another run is started while the original is still active. This ensures that the first run completes uninterrupted.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    thread = client.threads.create()

    run = client.runs.create(
        thread["thread_id"],
        "agent",
        input={"messages": [{"role": "user", "content": "what's the weather in sf?"}]}
    )

    try:
        client.runs.create(
            thread["thread_id"],
            "agent",
            input={"messages": [{"role": "user", "content": "what's the weather in nyc?"}]},
            multitask_strategy="reject",
        )
    except Exception as e:
        print("Failed to start concurrent run:", e)
    ```


??? "How to use the enqueue option"
	Full Example: [How to use the enqueue option](../cloud/how-tos/enqueue_concurrent.md)

    Use the "enqueue" strategy to queue and process multiple user requests in the order they arrive. The second request waits until the first is done, then runs automatically.

    ```python
    from langchain_core.messages import convert_to_messages
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="<DEPLOYMENT_URL>")
    assistant_id = "agent"

    # Create a new thread
    thread = client.threads.create()

    # Create two runs, with the second enqueued
    first_run = client.runs.create(
        thread["thread_id"],
        assistant_id,
        input={"messages": [{"role": "user", "content": "what's the weather in sf?"}]},
    )
    second_run = client.runs.create(
        thread["thread_id"],
        assistant_id,
        input={"messages": [{"role": "user", "content": "what's the weather in nyc?"}]},
        multitask_strategy="enqueue",
    )

    # Wait for second run to complete and view thread results
    client.runs.join(thread["thread_id"], second_run["run_id"])
    state = client.threads.get_state(thread["thread_id"])
    for msg in convert_to_messages(state["values"]["messages"]):
        print(msg)
    ```

### Webhooks

??? "How to integrate webhooks"
	Full Example: [How to integrate webhooks](../cloud/how-tos/webhooks.md)

    Expose an endpoint that can accept POST requests, then provide its URL in the **webhook** parameter to get a callback once your run finishes.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url="https://YOUR_DEPLOYMENT_URL")

    # Create a thread
    thread = client.threads.create()

    # Create a run with a webhook
    run_response = client.runs.wait(
        thread_id=thread["thread_id"],
        assistant_id="agent",
        input={"messages": [{"role": "user", "content": "Hello!"}]},
        webhook="https://my-server.app/my-webhook-endpoint"
    )
    print(run_response)
    ```

### Cron Jobs

??? "How to create cron jobs"
	Full Example: [How to create cron jobs](../cloud/how-tos/cron_jobs.md)

    **Cron jobs** allow you to schedule your graph to run on a set timetable (e.g., sending automated emails) rather than waiting for user input. Simply provide a cron expression to define your schedule, and always remember to delete old jobs to avoid excess usage.

    ```python
    from langgraph_sdk import get_sync_client

    client = get_sync_client(url=<DEPLOYMENT_URL>)
    assistant_id = "agent"

    # Create thread
    thread = client.threads.create()

    # Schedule a cron job for a thread
    cron_job = client.crons.create_for_thread(
        thread["thread_id"],
        assistant_id,
        schedule="27 15 * * *",
        input={"messages": [{"role": "user", "content": "What time is it?"}]},
    )

    # Delete the cron job when you're done
    client.crons.delete(cron_job["cron_id"])
    ``` 

### LangGraph Studio

LangGraph Studio is a built-in UI for visualizing, testing, and debugging your agents.

??? "How to connect to a LangGraph Cloud deployment"
	Full Example: [How to connect to a LangGraph Cloud deployment](../cloud/how-tos/test_deployment.md)

??? "How to connect to a local dev server"
	Full Example: [How to connect to a local dev server](../how-tos/local-studio.md)

??? "How to connect to a local deployment (Docker)"
	Full Example: [How to connect to a local deployment (Docker)](../cloud/how-tos/test_local_deployment.md)

??? "How to test your graph in LangGraph Studio (MacOS only)"
	Full Example: [How to test your graph in LangGraph Studio (MacOS only)](../cloud/how-tos/invoke_studio.md)

??? "How to interact with threads in LangGraph Studio"
	Full Example: [How to interact with threads in LangGraph Studio](../cloud/how-tos/threads_studio.md)

??? "How to add nodes as dataset examples in LangGraph Studio"
	Full Example: [How to add nodes as dataset examples in LangGraph Studio](../cloud/how-tos/datasets_studio.md)

## Troubleshooting

These are the guides for resolving common errors you may find while building with LangGraph. Errors referenced below will have an `lc_error_code` property corresponding to one of the below codes when they are thrown in code.

- [GRAPH_RECURSION_LIMIT](../troubleshooting/errors/GRAPH_RECURSION_LIMIT.md)
- [INVALID_CONCURRENT_GRAPH_UPDATE](../troubleshooting/errors/INVALID_CONCURRENT_GRAPH_UPDATE.md)
- [INVALID_GRAPH_NODE_RETURN_VALUE](../troubleshooting/errors/INVALID_GRAPH_NODE_RETURN_VALUE.md)
- [MULTIPLE_SUBGRAPHS](../troubleshooting/errors/MULTIPLE_SUBGRAPHS.md)
- [INVALID_CHAT_HISTORY](../troubleshooting/errors/INVALID_CHAT_HISTORY.md)
