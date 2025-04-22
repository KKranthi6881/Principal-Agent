from fastapi import APIRouter, HTTPException
import sqlite3
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Create router - IMPORTANT: Don't include the full path in router endpoints
router = APIRouter(prefix="/api")

# Test API endpoint
@router.get("/test")
async def test_api():
    """Simple test endpoint to verify API routing"""
    logger.info("Test API endpoint called")
    return {"status": "success", "message": "API routing is working correctly"}

# Test database connection
@router.get("/test-database")  
async def test_database():
    """Test database connection and check table structure"""
    logger.info("Testing database connection")
    try:
        # Check if database file exists
        db_path = os.path.join('database', 'conversations.db')
        if not os.path.exists(db_path):
            logger.error(f"Database file not found: {db_path}")
            return {
                "status": "error", 
                "detail": "Conversations database not found",
                "path": db_path,
                "exists": False
            }
            
        # Try to open the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check for required tables
        tables = {}
        for table in ['threads', 'conversations', 'agent_logs']:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            tables[table] = cursor.fetchone() is not None
        
        # Get counts for each table
        counts = {}
        for table in tables:
            if tables[table]:
                cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
                counts[table] = cursor.fetchone()['count']
            else:
                counts[table] = None
        
        conn.close()
        
        return {
            "status": "success",
            "database_path": db_path,
            "database_exists": True,
            "tables_exist": tables,
            "row_counts": counts
        }
    except Exception as e:
        logger.error(f"Error testing database: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"status": "error", "detail": str(e)}

@router.get("/thread-conversations")
async def get_all_thread_conversations():
    """
    Get all conversation threads with their latest messages
    Returns a list of thread IDs, latest questions, and conversation counts
    """
    logger.info("Received request for /api/thread-conversations")
    try:
        # Check if database file exists
        db_path = os.path.join('database', 'conversations.db')
        db_abs_path = os.path.abspath(db_path)
        logger.info(f"Looking for database at absolute path: {db_abs_path}")
        
        if not os.path.exists(db_abs_path):
            logger.error(f"Database file not found: {db_abs_path}")
            return {"status": "error", "detail": f"Conversations database not found at {db_abs_path}"}
            
        logger.info(f"Opening database at {db_abs_path}")
        conn = sqlite3.connect(db_abs_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if conversations table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='conversations'")
        if not cursor.fetchone():
            logger.error("Conversations table does not exist in database")
            return {"status": "error", "detail": "Conversations table not found in database"}
            
        # Get distinct thread_ids from conversations table
        cursor.execute("SELECT DISTINCT thread_id FROM conversations")
        unique_thread_ids = [row['thread_id'] for row in cursor.fetchall()]
        logger.info(f"Found {len(unique_thread_ids)} unique thread_ids in conversations table")
        
        threads = []
        for thread_id in unique_thread_ids:
            # Get conversation count
            cursor.execute("SELECT COUNT(*) as count FROM conversations WHERE thread_id = ?", (thread_id,))
            count_row = cursor.fetchone()
            conversation_count = count_row["count"] if count_row else 0
            
            # Get latest user message
            cursor.execute("""
                SELECT content, created_at FROM conversations 
                WHERE thread_id = ? AND role = 'user'
                ORDER BY created_at DESC LIMIT 1
            """, (thread_id,))
            latest_user_msg = cursor.fetchone()
            
            # Get the first conversation ID
            cursor.execute("""
                SELECT conversation_id, created_at FROM conversations 
                WHERE thread_id = ? 
                ORDER BY created_at ASC LIMIT 1
            """, (thread_id,))
            first_conv = cursor.fetchone()
            
            # Get the latest timestamp of any message
            cursor.execute("""
                SELECT created_at FROM conversations 
                WHERE thread_id = ? 
                ORDER BY created_at DESC LIMIT 1
            """, (thread_id,))
            latest_timestamp_row = cursor.fetchone()
            
            # Use thread_id as topic if there's no matching record in threads table
            topic = f"Conversation {thread_id.split('-')[0]}" if thread_id else "Untitled conversation"
            
            # Get thread creation timestamp (earliest conversation in this thread)
            cursor.execute("""
                SELECT created_at FROM conversations 
                WHERE thread_id = ? 
                ORDER BY created_at ASC LIMIT 1
            """, (thread_id,))
            thread_created_row = cursor.fetchone()
            thread_created_at = thread_created_row["created_at"] if thread_created_row else None
            
            # Build thread object
            thread_obj = {
                "thread_id": thread_id,
                "topic": topic,
                "thread_created_at": thread_created_at,
                "conversation_count": conversation_count,
                "latest_question": latest_user_msg["content"] if latest_user_msg else None,
                "latest_timestamp": latest_timestamp_row["created_at"] if latest_timestamp_row else None,
                "first_conversation_id": first_conv["conversation_id"] if first_conv else None
            }
            
            # Log details for debugging
            logger.info(f"Thread {thread_id}: {conversation_count} conversations, latest question: {thread_obj['latest_question'][:20] + '...' if thread_obj['latest_question'] else None}")
            
            threads.append(thread_obj)
        
        # Sort threads by latest timestamp
        threads.sort(key=lambda x: x["latest_timestamp"] if x["latest_timestamp"] else "", reverse=True)
        
        logger.info(f"Returning {len(threads)} threads with conversation data")
        return {"status": "success", "threads": threads}
    except Exception as e:
        logger.error(f"Error getting thread conversations: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if 'conn' in locals():
            logger.info("Closing database connection")
            conn.close()

@router.get("/thread/{thread_id}/conversations")
async def get_thread_conversations_api(thread_id: str):
    """
    Get all conversations for a specific thread
    
    Args:
        thread_id: ID of the thread
        
    Returns:
        List of conversations
    """
    try:
        db_path = os.path.join('database', 'conversations.db')
        db_abs_path = os.path.abspath(db_path)
        logger.info(f"Fetching conversations for thread {thread_id} from {db_abs_path}")
        
        conn = sqlite3.connect(db_abs_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if any conversations exist for this thread ID
        cursor.execute("SELECT COUNT(*) as count FROM conversations WHERE thread_id = ?", (thread_id,))
        count = cursor.fetchone()['count']
        
        if count == 0:
            # Also try looking for conversations where the thread_id is a prefix
            thread_id_prefix = thread_id.split('-')[0]
            cursor.execute("SELECT COUNT(*) as count FROM conversations WHERE thread_id LIKE ?", (f"{thread_id_prefix}%",))
            prefix_count = cursor.fetchone()['count']
            
            if prefix_count > 0:
                # Use the prefix instead
                logger.info(f"Using thread_id prefix {thread_id_prefix} found {prefix_count} conversations")
                thread_id = thread_id_prefix
            else:
                logger.warning(f"No conversations found for thread {thread_id}")
                return {"status": "success", "thread_id": thread_id, "conversations": []}
        
        # Get all conversations for this thread
        cursor.execute("""
            SELECT 
                c.conversation_id,
                c.thread_id,
                c.user_id,
                c.role,
                c.content,
                c.created_at
            FROM conversations c
            WHERE c.thread_id = ? OR c.thread_id LIKE ?
            ORDER BY c.created_at ASC
        """, (thread_id, f"{thread_id}%"))
        
        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                "conversation_id": row["conversation_id"],
                "thread_id": row["thread_id"],
                "user_id": row["user_id"],
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["created_at"]
            })
        
        logger.info(f"Found {len(conversations)} conversations for thread {thread_id}")
        return {"status": "success", "thread_id": thread_id, "conversations": conversations}
    except Exception as e:
        logger.error(f"Error getting conversations for thread {thread_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if 'conn' in locals():
            conn.close()

@router.get("/debug-conversations")
async def debug_conversations():
    """
    Debug endpoint to check the association between threads and conversations
    """
    logger.info("Debugging thread-conversation relationships")
    try:
        # Check if database file exists
        db_path = os.path.join('database', 'conversations.db')
        db_abs_path = os.path.abspath(db_path)
        logger.info(f"Looking for database at absolute path: {db_abs_path}")
        
        if not os.path.exists(db_abs_path):
            logger.error(f"Database file not found: {db_abs_path}")
            return {"status": "error", "detail": f"Conversations database not found at {db_abs_path}"}
            
        logger.info(f"Opening database at {db_abs_path}")
        conn = sqlite3.connect(db_abs_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all conversation data with thread info
        cursor.execute("""
            SELECT 
                c.conversation_id, 
                c.thread_id, 
                c.role, 
                c.content,
                c.created_at
            FROM conversations c
            ORDER BY c.thread_id, c.created_at
            LIMIT 100
        """)
        
        conversations = []
        for row in cursor.fetchall():
            conversations.append({
                "conversation_id": row["conversation_id"],
                "thread_id": row["thread_id"],
                "role": row["role"],
                "content": row["content"][:50] + "..." if len(row["content"]) > 50 else row["content"],
                "created_at": row["created_at"]
            })
        
        # Get count of conversations by thread_id
        cursor.execute("""
            SELECT 
                thread_id, 
                COUNT(*) as count,
                MIN(created_at) as first_message,
                MAX(created_at) as last_message
            FROM conversations 
            GROUP BY thread_id
            ORDER BY count DESC
        """)
        
        thread_stats = []
        for row in cursor.fetchall():
            thread_stats.append({
                "thread_id": row["thread_id"],
                "conversation_count": row["count"],
                "first_message": row["first_message"],
                "last_message": row["last_message"]
            })
        
        # Get thread table info
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='threads'")
        threads_table_exists = cursor.fetchone() is not None
        
        thread_records = []
        if threads_table_exists:
            cursor.execute("SELECT thread_id, topic, created_at FROM threads")
            for row in cursor.fetchall():
                thread_records.append({
                    "thread_id": row["thread_id"],
                    "topic": row["topic"],
                    "created_at": row["created_at"]
                })
        
        # Get role distribution
        cursor.execute("""
            SELECT 
                role, 
                COUNT(*) as count
            FROM conversations 
            GROUP BY role
        """)
        
        role_stats = {}
        for row in cursor.fetchall():
            role_stats[row["role"]] = row["count"]
        
        # Get user/assistant exchanges
        cursor.execute("""
            SELECT 
                thread_id,
                SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) as user_messages,
                SUM(CASE WHEN role = 'assistant' THEN 1 ELSE 0 END) as assistant_messages
            FROM conversations
            GROUP BY thread_id
            ORDER BY thread_id
        """)
        
        exchange_stats = []
        for row in cursor.fetchall():
            exchange_stats.append({
                "thread_id": row["thread_id"],
                "user_messages": row["user_messages"],
                "assistant_messages": row["assistant_messages"]
            })
        
        return {
            "status": "success",
            "conversation_sample": conversations,
            "thread_stats": thread_stats,
            "thread_records": thread_records,
            "threads_table_exists": threads_table_exists,
            "role_distribution": role_stats,
            "exchange_stats": exchange_stats,
            "total_threads": len(thread_stats),
            "total_conversations": sum(stat["conversation_count"] for stat in thread_stats)
        }
        
    except Exception as e:
        logger.error(f"Error debugging conversations: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        if 'conn' in locals():
            logger.info("Closing database connection")
            conn.close()