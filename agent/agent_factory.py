"""
Factory for creating and configuring LangGraph agents.
"""

import logging
from typing import Any, Dict
from psycopg_pool import AsyncConnectionPool
from langgraph.graph import StateGraph
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langmem import create_manage_memory_tool
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import SystemMessage

from db.postgres_utils import create_memory_store

import os as _os
from agent.prompts import FINANCE_SYSTEM_PROMPT, VES_SYSTEM_PROMPT
from agent.contract_tool import search_contracts, get_contracts_stats

_DEPT_PROMPTS = {
    "finance": FINANCE_SYSTEM_PROMPT,
    "ves": VES_SYSTEM_PROMPT,
}
MEMORY_SYSTEM_PROMPT = _DEPT_PROMPTS.get(_os.getenv("DEPT_MODE", "finance"), FINANCE_SYSTEM_PROMPT)

logger = logging.getLogger(__name__)

class AgentFactory:
    """Factory for creating and configuring LangGraph agents"""
    
    @staticmethod
    async def create_agent(
        pg_connection: str,
        pool: AsyncConnectionPool,
        llm_model: str,
        vector_dims: int,
        embed_model: str,
        user_id: str
    ) -> Any:
        """Initialize LangGraph agent with memory and checkpoints
        
        Args:
            pg_connection: PostgreSQL connection string
            pool: Connection pool for database operations
            llm_model: LLM model identifier
            vector_dims: Dimensions of the vector embeddings
            embed_model: Name of the embedding model
            user_id: User identifier for memory namespace (required)
            
        Returns:
            The created agent
        """
        if not user_id:
            raise ValueError("user_id is required for agent creation")
            
        checkpointer = AsyncPostgresSaver(pool)
        
        # Create the memory store with the connection pool
        store = await create_memory_store(pg_connection, pool, vector_dims, embed_model)
        
        # Use user_id as namespace (no fallback to "memories")
        namespace = (str(user_id),)
        
        # Simple system prompt — inject as SystemMessage prepended to messages
        system_prompt = MEMORY_SYSTEM_PROMPT.format(memory_content="")
        
        # LLM via OpenRouter (openai-compatible) or Anthropic directly
        import os
        from langchain_openai import ChatOpenAI
        from langchain_anthropic import ChatAnthropic

        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_base_url = os.getenv("OPENAI_BASE_URL", "")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")

        if anthropic_key and "openrouter" not in openai_base_url:
            llm = ChatAnthropic(model=llm_model, api_key=anthropic_key)
        else:
            # OpenRouter via OpenAI-compatible endpoint
            llm = ChatOpenAI(
                model=llm_model,
                base_url=openai_base_url or "https://openrouter.ai/api/v1",
                api_key=openrouter_key or os.getenv("OPENAI_API_KEY"),
            )

        return create_react_agent(
            llm,
            prompt=system_prompt,
            tools=[create_manage_memory_tool(namespace=namespace), search_contracts, get_contracts_stats],
            checkpointer=checkpointer,
            store=store
        )
    
    @staticmethod
    async def create_advanced_graph(
        pg_connection: str,
        pool: AsyncConnectionPool,
        vector_dims: int,
        embed_model: str
    ) -> StateGraph:
        """
        Create a more complex LangGraph for advanced conversational capabilities.
        
        This is where you can improve the graph and make it more complex:
        - Add multiple nodes for different processing steps
        - Implement conditional routing based on message content
        - Add specialized handlers for different types of queries
        - Implement multi-step reasoning
        - Add external API integrations
        
        Args:
            pg_connection: PostgreSQL connection string
            pool: Connection pool for database operations
            vector_dims: Dimensions of the vector embeddings
            embed_model: Name of the embedding model
            
        Returns:
            StateGraph: The created graph
        """
        # This is a placeholder for your improved graph implementation
        graph = StateGraph(Any)
        
        # Create the memory store for the graph with the connection pool
        store = await create_memory_store(pg_connection, pool, vector_dims, embed_model)
        
        # Example of how you might expand this:
        # 
        # # Define nodes
        # graph.add_node("classify_intent", classify_user_intent)
        # graph.add_node("answer_question", answer_general_question)
        # graph.add_node("search_knowledge", search_knowledge_base)
        # graph.add_node("generate_response", generate_final_response)
        # 
        # # Define edges
        # graph.add_edge("classify_intent", "answer_question")
        # graph.add_conditional_edges(
        #     "classify_intent",
        #     route_by_intent,
        #     {
        #         "question": "answer_question",
        #         "search": "search_knowledge",
        #         "task": "perform_task"
        #     }
        # )
        # graph.add_edge("search_knowledge", "generate_response")
        # graph.add_edge("answer_question", "generate_response")
        
        # Set the entry point
        # graph.set_entry_point("classify_intent")
        
        # Set the store for the graph
        # graph.set_store(store)
        
        return graph
