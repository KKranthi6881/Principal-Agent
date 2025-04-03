We are building a Agentic AI application for Data Management process including Data Code development, Understanding the Data logic, code logic, business context , code block search, Providing the lineage info at column level. 
Here is the tech stack installed and built it:

1. /Users/Kranthi_1/Data-Architect/frontend 
        - Built a frontend UI to interact the backend for Chat with AI Agents. Built it in React and Node JS. 
        - We built three tabs Chat, Connector and Hitosry
        - Chat - provide Chat interaction between user and backend AI agents.
        - Connector - Curretnly built to connect the Github repo for the interating with github code
        - History - Pull the Chat history conversations.

2.  /Users/Kranthi_1/Data-Architect/database
        - Using Supabase for local database 
        - We need to use tables for chat conversation store, user info
        - We need to use Pgvector for VectorDB storage
        - We need to build the code, functions in backend python code to process them properly
3.  /Users/Kranthi_1/Data-Architect/backend

        - We need to use this backend for processing the backend process including define the tools, Agents, Database & Vector store and retrival
        - We must use python for backend programming language
        - We need to use FastAPI for API services
        - Tools:  We need to create tools with processing the github .sql files to get the lineage, code info, metadata , file path, code search etc. 
                  - We can leverage the langchain github tool sets most of the cases for interacting with github.
                  - We need to use the SQLGlot for processing and capturing the lineage info from the github file script. it should support Snowflake, dbt, PostgreSQL, SQLServer (TSQL), MYSQL
                  - Entire tools set should define small files for each type of database 
                  - Build a tool for providing the lineage info into JSON output for UI visualization
        - Agents: The main goal of the Agents to provide the answers for user based on their question.
                  - We need to use the latest langchain, langgraph frameworks to build the AI AGents.
                  - Agents types including - Code Eplanier, dependcy explaining, summarizing the logic context with deep exxlanations
                  - All Agents must follow the latest langgraph nodes, edges with tracking the logging info and they must support the local langgraph studio
                  - All agents must follow the Thread ID, Conversation ID and User ID to track the conversations. Thread ID for Specific overall topic, Coversation ID for each output chat text from AI and User, UserID should come from User info
                  - All AGents must use Supabase tables for storing the conversation history and also pulling the last 6 conversations for providing the next answer
        - FastAPI : API's must be flexible and process dynamically and also we need to show the API calling in UI for different meaning of text
                    - We need to create multiple files for different types of API's. Instead of large files, better to define like services API
                    - All API calling must be track and log the info to display the info to user in UI
                    - API's should have meaningfull name
        - Vector Store:  Vector must be use PGVector and we need to define the different vector stores for different type of store for better retrival.
                    - We need to classify the vector stores seperate for Document store, github store.
                    - DOcument store should use hybrid search for better results
                    - Github code search should search similarity search
          
                  