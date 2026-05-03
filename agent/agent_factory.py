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
from agent.prompts import FINANCE_SYSTEM_PROMPT, VES_SYSTEM_PROMPT, RAILWAY_SYSTEM_PROMPT, MARITIME_SYSTEM_PROMPT, FREIGHT_SYSTEM_PROMPT
from agent.contract_tool import search_contracts, get_contracts_stats, search_contracts_filtered
from agent.receivables_tool import get_receivables_stats, search_receivables, get_critical_receivables
from agent.assets_tool import get_assets_summary, search_assets, get_assets_by_category, get_top_assets
from agent.acwag_tool import get_acwag_stats, search_acwag_by_company, search_acwag_filtered
from agent.railway_tools import add_trk_code, revoke_trk_code, get_aswak_stats, add_apparel_wagon, get_apparel_list, calculate_commission, get_railway_receivables, update_railway_receivable_status
from agent.maritime_tools import (get_maritime_receivables, update_maritime_receivable_status, add_maritime_receivable, add_balkansk_operation, sync_balkansk_operations, get_balkansk_list, add_container, update_container_status, get_container_list, get_container_stats, calculate_port_service, calculate_storage_fee, calculate_container_handling, calculate_bl_fee, add_voyage, get_voyage_report, get_maritime_summary)
from agent.freight_tools import check_route_feasibility, estimate_cost, check_required_docs
from agent.freight_crm_tools import register_client, save_freight_request, find_similar_requests

_DEPT_PROMPTS = {
    "finance": FINANCE_SYSTEM_PROMPT,
    "ves":     VES_SYSTEM_PROMPT,
    "railway": RAILWAY_SYSTEM_PROMPT,
    "maritime": MARITIME_SYSTEM_PROMPT,
    "freight": FREIGHT_SYSTEM_PROMPT,
}

_DEPT_MODE = _os.getenv("DEPT_MODE", "finance")
MEMORY_SYSTEM_PROMPT = _DEPT_PROMPTS.get(_DEPT_MODE, FINANCE_SYSTEM_PROMPT)

# Инструменты по отделам — каждый бот получает только свои tools
_DEPT_TOOLS = {
    "finance": [get_receivables_stats, search_receivables, get_critical_receivables,
                get_assets_summary, search_assets, get_assets_by_category, get_top_assets],
    "ves":     [search_contracts, search_contracts_filtered, get_contracts_stats],
    "railway": [search_contracts, search_contracts_filtered, get_contracts_stats,
                get_acwag_stats, search_acwag_by_company, search_acwag_filtered,
                add_trk_code, revoke_trk_code, get_aswak_stats,
                add_apparel_wagon, get_apparel_list, calculate_commission,
                get_railway_receivables, update_railway_receivable_status],
    "maritime": [get_maritime_receivables, update_maritime_receivable_status, add_maritime_receivable,
                 add_balkansk_operation, sync_balkansk_operations, get_balkansk_list,
                 add_container, update_container_status, get_container_list, get_container_stats,
                 calculate_port_service, calculate_storage_fee, calculate_container_handling, calculate_bl_fee,
                 add_voyage, get_voyage_report, get_maritime_summary],
    "freight": [
        check_route_feasibility, estimate_cost, check_required_docs,
        register_client, save_freight_request, find_similar_requests,
    ],
}

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
        if not user_id:
            raise ValueError("user_id is required for agent creation")
            
        checkpointer = AsyncPostgresSaver(pool)
        store = await create_memory_store(pg_connection, pool, vector_dims, embed_model)
        namespace = (str(user_id),)
        system_prompt = MEMORY_SYSTEM_PROMPT.format(memory_content="")
        
        import os
        from langchain_openai import ChatOpenAI
        from langchain_anthropic import ChatAnthropic

        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        effective_api_key = openrouter_key or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY", "")

        if anthropic_key and "openrouter" not in openai_base_url:
            llm = ChatAnthropic(model=llm_model, api_key=anthropic_key)
        else:
            llm = ChatOpenAI(
                model=llm_model,
                base_url=openai_base_url,
                api_key=effective_api_key,
            )

        dept_tools = _DEPT_TOOLS.get(_DEPT_MODE, [])
        all_tools = [create_manage_memory_tool(namespace=namespace)] + dept_tools

        return create_react_agent(
            llm,
            prompt=system_prompt,
            tools=all_tools,
            checkpointer=checkpointer,
            store=store
        )
