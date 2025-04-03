
  /Users/Kranthi_1/Data-Architect/backend
   I need you do follow these steps to implement the successfull backend integration with local sqlite database. use the python and FASTAPI as tech stack. Before you implement these steps first create a folder structure properly then provide folder structure script for auto creation
 

   Step1: 
        - Database Path: /Users/Kranthi_1/Data-Architect/backend/database
        - We have created conversations.db, log_info.db and metadata.db sqlite databases for backend
        - conversations.db: We need create the tables respetive to the chat conversation, chat history at thread ID level. All agents must follow the Thread ID, Conversation ID and User ID to track the conversations. 
                            Thread ID for Specific overall topic,  coversation ID for each output chat text from AI and User,UserID should come from User info
        - log_info.db: We need to capture each and every agentic logging info to track it. it should be including each agent output, user input, tool calling info etc
        - metadata.db:  We need to capture the info of user details, connections like github, snowflake etc
        
   Step2:
        - We need to create three chromadb vector store databases. Create a new folder with below databases.
        - chromadb_github: This will allow to store github related files including code, filepath url, git file metadata
        - chromadb_document: This allow to store the document data into vector including pdfs
        - chromadb_summary: This allow to store the summary info of the thread conversation
       

   Step2: 
        Tools: 
        - We need to create tools with processing the github .sql files to get the lineage, code info, metadata , file path, code search etc.
        - We can leverage the langchain github tool sets most of the cases for interacting with github.
        - We need to use the SQLGlot for processing and capturing the lineage info from the github file script. it should support Snowflake, dbt, PostgreSQL, SQLServer (TSQL), MYSQL
        - Entire tools set should define small files for each type of database
        - Build a tool for providing the lineage info into JSON output for UI visualization
  Step3:
     
        Agents: 
        - The main goal of the Agents to provide the answers for user based on their question.
        - We need to use the latest langchain, langgraph frameworks to build the AI AGents.
        - Agents types including - Code Eplanier, dependcy explaining, summarizing the logic context with deep exxlanations
        - All Agents must follow the latest langgraph nodes, edges with tracking the logging info and they must support the local langgraph studio
        - All agents must follow the Thread ID, Conversation ID and User ID to track the conversations. Thread ID for Specific overall topic, Coversation ID for each output chat text from AI and User,    UserID should come from User info
        - All AGents must use Supabase tables for storing the conversation history and also pulling the last 6 conversations for providing the next answer
  Step4:
   
       FastAPI : API's must be flexible and process dynamically and also we need to show the API calling in UI for different meaning of text
        - We need to create multiple files for different types of API's. Instead of large files, better to define like services API
        - All API calling must be track and log the info to display the info to user in UI
        - API's should have meaningfull name
        - Vector Store: Vector must be use PGVector and we need to define the different vector stores for different type of store for better retrival.
        - We need to classify the vector stores seperate for Document store, github store.
        - DOcument store should use hybrid search for better results
        - Github code search should search similarity search