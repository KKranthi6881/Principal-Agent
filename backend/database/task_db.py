"""
Database handler for task progress tracking
"""

import os
import sqlite3
import json
import time
import logging
from typing import Dict, List, Any, Optional
import uuid

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class TaskDB:
    """
    Database handler for storing and retrieving task progress information
    """
    
    def __init__(self, db_path: str = os.path.join('database', 'tasks.db')):
        self.db_path = db_path
        
        # Ensure database directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize database tables
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Create tasks table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            connector_id TEXT,
            repo_url TEXT,
            tech_stack TEXT,
            total_items INTEGER DEFAULT 0,
            processed_items INTEGER DEFAULT 0,
            successful_items INTEGER DEFAULT 0,
            failed_items INTEGER DEFAULT 0,
            error TEXT,
            metadata TEXT
        )
        ''')
        
        # Create task_chunks table for tracking individual chunks
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_chunks (
            chunk_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            chunk_number INTEGER NOT NULL,
            total_chunks INTEGER NOT NULL,
            item_count INTEGER DEFAULT 0,
            processed_count INTEGER DEFAULT 0,
            error TEXT,
            metadata TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(task_id)
        )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_connector_id ON tasks(connector_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_chunks_task_id ON task_chunks(task_id)')
        
        conn.commit()
        conn.close()
    
    def _get_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_task(self, task_type: str, connector_id: str = None, repo_url: str = None, 
                   tech_stack: str = None, metadata: Dict[str, Any] = None) -> str:
        """
        Create a new task in the database
        
        Args:
            task_type: Type of task (e.g., 'lineage_extraction')
            connector_id: GitHub connector ID (optional)
            repo_url: Repository URL (optional)
            tech_stack: Tech stack (optional)
            metadata: Additional metadata as JSON (optional)
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        current_time = time.time()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                '''
                INSERT INTO tasks 
                (task_id, task_type, status, created_at, updated_at, connector_id, 
                repo_url, tech_stack, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    task_id, 
                    task_type, 
                    'pending', 
                    current_time, 
                    current_time, 
                    connector_id, 
                    repo_url, 
                    tech_stack, 
                    json.dumps(metadata) if metadata else None
                )
            )
            conn.commit()
            return task_id
        except Exception as e:
            logger.error(f"Error creating task: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def update_task(self, task_id: str, status: str = None, total_items: int = None,
                   processed_items: int = None, successful_items: int = None, 
                   failed_items: int = None, error: str = None, progress: int = None,
                   current_step: str = None, metadata: Dict[str, Any] = None) -> bool:
        """
        Update an existing task
        
        Args:
            task_id: Task ID
            status: New status (optional)
            total_items: Total number of items (optional)
            processed_items: Number of processed items (optional)
            successful_items: Number of successful items (optional)
            failed_items: Number of failed items (optional)
            error: Error message (optional)
            progress: Progress percentage 0-100 (optional)
            current_step: Current processing step name (optional)
            metadata: Additional metadata to merge with existing (optional)
            
        Returns:
            Success flag
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current task data if we need to update metadata
            current_metadata = None
            if metadata is not None:
                cursor.execute("SELECT metadata FROM tasks WHERE task_id = ?", (task_id,))
                result = cursor.fetchone()
                if result and result['metadata']:
                    current_metadata = json.loads(result['metadata'])
                    
                # Merge metadata
                if current_metadata:
                    current_metadata.update(metadata)
                    metadata = current_metadata
            
            # Build update query dynamically
            update_fields = []
            params = []
            
            # Always update the updated_at timestamp
            update_fields.append("updated_at = ?")
            params.append(time.time())
            
            if status is not None:
                update_fields.append("status = ?")
                params.append(status)
            
            if total_items is not None:
                update_fields.append("total_items = ?")
                params.append(total_items)
            
            if processed_items is not None:
                update_fields.append("processed_items = ?")
                params.append(processed_items)
            
            if successful_items is not None:
                update_fields.append("successful_items = ?")
                params.append(successful_items)
            
            if failed_items is not None:
                update_fields.append("failed_items = ?")
                params.append(failed_items)
            
            # Support progress parameter (percentage 0-100)
            if progress is not None:
                # Store progress in metadata if it's not there
                if metadata is None:
                    metadata = {}
                metadata['progress'] = progress
            
            # Support current_step parameter (current processing step)
            if current_step is not None:
                # Store current_step in metadata if it's not there
                if metadata is None:
                    metadata = {}
                metadata['current_step'] = current_step
            
            if error is not None:
                update_fields.append("error = ?")
                params.append(error)
            
            if metadata is not None:
                update_fields.append("metadata = ?")
                params.append(json.dumps(metadata))
            
            # Only proceed if there are fields to update
            if update_fields:
                query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE task_id = ?"
                params.append(task_id)
                
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
            
            return False
        except Exception as e:
            logger.error(f"Error updating task: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def increment_task_progress(self, task_id: str, processed: int = 1, 
                               successful: int = 0, failed: int = 0) -> bool:
        """
        Increment task progress counters
        
        Args:
            task_id: Task ID
            processed: Number of processed items to add
            successful: Number of successful items to add
            failed: Number of failed items to add
            
        Returns:
            Success flag
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                '''
                UPDATE tasks SET 
                processed_items = processed_items + ?,
                successful_items = successful_items + ?,
                failed_items = failed_items + ?,
                updated_at = ?
                WHERE task_id = ?
                ''',
                (processed, successful, failed, time.time(), task_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error incrementing task progress: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task details by ID
        
        Args:
            task_id: Task ID
            
        Returns:
            Task details as dictionary or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
            task = cursor.fetchone()
            
            if not task:
                return None
            
            # Convert to dict and parse metadata JSON
            task_dict = dict(task)
            if task_dict.get('metadata'):
                task_dict['metadata'] = json.loads(task_dict['metadata'])
            else:
                task_dict['metadata'] = {}
            
            # Get task chunks
            cursor.execute("SELECT * FROM task_chunks WHERE task_id = ? ORDER BY chunk_number", (task_id,))
            chunks = cursor.fetchall()
            
            if chunks:
                task_dict['chunks'] = []
                for chunk in chunks:
                    chunk_dict = dict(chunk)
                    if chunk_dict.get('metadata'):
                        chunk_dict['metadata'] = json.loads(chunk_dict['metadata'])
                    else:
                        chunk_dict['metadata'] = {}
                    task_dict['chunks'].append(chunk_dict)
            
            return task_dict
        except Exception as e:
            logger.error(f"Error getting task: {str(e)}")
            return None
        finally:
            conn.close()
    
    def list_tasks(self, status: str = None, connector_id: str = None, 
                  task_type: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        List tasks with optional filtering
        
        Args:
            status: Filter by status (optional)
            connector_id: Filter by connector ID (optional)
            task_type: Filter by task type (optional)
            limit: Maximum number of tasks to return
            
        Returns:
            List of task dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Build query with filters
            query = "SELECT * FROM tasks"
            params = []
            
            filters = []
            if status:
                filters.append("status = ?")
                params.append(status)
            
            if connector_id:
                filters.append("connector_id = ?")
                params.append(connector_id)
            
            if task_type:
                filters.append("task_type = ?")
                params.append(task_type)
            
            if filters:
                query += " WHERE " + " AND ".join(filters)
            
            # Add ordering and limit
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            tasks = cursor.fetchall()
            
            # Convert to list of dicts and parse metadata JSON
            result = []
            for task in tasks:
                task_dict = dict(task)
                if task_dict.get('metadata'):
                    task_dict['metadata'] = json.loads(task_dict['metadata'])
                else:
                    task_dict['metadata'] = {}
                result.append(task_dict)
            
            return result
        except Exception as e:
            logger.error(f"Error listing tasks: {str(e)}")
            return []
        finally:
            conn.close()
    
    def create_task_chunk(self, task_id: str, chunk_number: int, total_chunks: int, 
                         item_count: int, metadata: Dict[str, Any] = None) -> str:
        """
        Create a new task chunk
        
        Args:
            task_id: Parent task ID
            chunk_number: Chunk number (0-based)
            total_chunks: Total number of chunks
            item_count: Number of items in this chunk
            metadata: Additional metadata (optional)
            
        Returns:
            Chunk ID
        """
        chunk_id = str(uuid.uuid4())
        current_time = time.time()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                '''
                INSERT INTO task_chunks
                (chunk_id, task_id, status, created_at, updated_at, chunk_number, 
                total_chunks, item_count, processed_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    chunk_id, 
                    task_id, 
                    'pending', 
                    current_time, 
                    current_time, 
                    chunk_number, 
                    total_chunks, 
                    item_count, 
                    0, 
                    json.dumps(metadata) if metadata else None
                )
            )
            conn.commit()
            return chunk_id
        except Exception as e:
            logger.error(f"Error creating task chunk: {str(e)}")
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def delete_task(self, task_id: str) -> bool:
        """
        Delete a task and its associated chunks
        
        Args:
            task_id: Task ID to delete
            
        Returns:
            Success flag
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # First delete associated chunks
            cursor.execute("DELETE FROM task_chunks WHERE task_id = ?", (task_id,))
            
            # Then delete the task
            cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            conn.commit()
            
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting task: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def update_task_chunk(self, chunk_id: str, status: str = None, 
                         processed_count: int = None, error: str = None,
                         metadata: Dict[str, Any] = None) -> bool:
        """
        Update a task chunk
        
        Args:
            chunk_id: Chunk ID
            status: New status (optional)
            processed_count: Number of processed items (optional)
            error: Error message (optional)
            metadata: Additional metadata to merge with existing (optional)
            
        Returns:
            Success flag
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current chunk data if we need to update metadata
            current_metadata = None
            if metadata is not None:
                cursor.execute("SELECT metadata FROM task_chunks WHERE chunk_id = ?", (chunk_id,))
                result = cursor.fetchone()
                if result and result['metadata']:
                    current_metadata = json.loads(result['metadata'])
                    
                # Merge metadata
                if current_metadata:
                    current_metadata.update(metadata)
                    metadata = current_metadata
            
            # Build update query dynamically
            update_fields = []
            params = []
            
            # Always update the updated_at timestamp
            update_fields.append("updated_at = ?")
            params.append(time.time())
            
            if status is not None:
                update_fields.append("status = ?")
                params.append(status)
            
            if processed_count is not None:
                update_fields.append("processed_count = ?")
                params.append(processed_count)
            
            if error is not None:
                update_fields.append("error = ?")
                params.append(error)
            
            if metadata is not None:
                update_fields.append("metadata = ?")
                params.append(json.dumps(metadata))
            
            # Only proceed if there are fields to update
            if update_fields:
                query = f"UPDATE task_chunks SET {', '.join(update_fields)} WHERE chunk_id = ?"
                params.append(chunk_id)
                
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount > 0
            
            return False
        except Exception as e:
            logger.error(f"Error updating task chunk: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def increment_chunk_progress(self, chunk_id: str, processed_count: int = 1) -> bool:
        """
        Increment chunk processed count
        
        Args:
            chunk_id: Chunk ID
            processed_count: Number of processed items to add
            
        Returns:
            Success flag
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                '''
                UPDATE task_chunks SET 
                processed_count = processed_count + ?,
                updated_at = ?
                WHERE chunk_id = ?
                ''',
                (processed_count, time.time(), chunk_id)
            )
            conn.commit()
            
            # Get the task_id for this chunk to update the parent task
            cursor.execute("SELECT task_id FROM task_chunks WHERE chunk_id = ?", (chunk_id,))
            result = cursor.fetchone()
            
            if result:
                # Also increment the parent task's processed items count
                task_id = result['task_id']
                self.increment_task_progress(task_id, processed=processed_count)
            
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error incrementing chunk progress: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_task_chunks(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a task
        
        Args:
            task_id: Task ID
            
        Returns:
            List of chunk dictionaries
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "SELECT * FROM task_chunks WHERE task_id = ? ORDER BY chunk_number",
                (task_id,)
            )
            chunks = cursor.fetchall()
            
            # Convert to list of dicts and parse metadata JSON
            result = []
            for chunk in chunks:
                chunk_dict = dict(chunk)
                if chunk_dict.get('metadata'):
                    chunk_dict['metadata'] = json.loads(chunk_dict['metadata'])
                else:
                    chunk_dict['metadata'] = {}
                result.append(chunk_dict)
            
            return result
        except Exception as e:
            logger.error(f"Error getting task chunks: {str(e)}")
            return []
        finally:
            conn.close()
    
    def clean_old_tasks(self, days_to_keep: int = 7) -> int:
        """
        Clean up old completed tasks
        
        Args:
            days_to_keep: Number of days to keep completed tasks
            
        Returns:
            Number of tasks deleted
        """
        cutoff_time = time.time() - (days_to_keep * 24 * 60 * 60)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get task IDs to delete
            cursor.execute(
                "SELECT task_id FROM tasks WHERE status IN ('completed', 'failed') AND updated_at < ?",
                (cutoff_time,)
            )
            tasks_to_delete = [row['task_id'] for row in cursor.fetchall()]
            
            deleted_count = 0
            
            # Delete task chunks first (foreign key constraint)
            for task_id in tasks_to_delete:
                cursor.execute("DELETE FROM task_chunks WHERE task_id = ?", (task_id,))
            
            # Then delete the tasks
            if tasks_to_delete:
                placeholders = ','.join(['?'] * len(tasks_to_delete))
                cursor.execute(f"DELETE FROM tasks WHERE task_id IN ({placeholders})", tasks_to_delete)
                deleted_count = cursor.rowcount
            
            conn.commit()
            return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning old tasks: {str(e)}")
            conn.rollback()
            return 0
        finally:
            conn.close()
