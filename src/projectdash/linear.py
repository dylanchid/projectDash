import httpx
import os
from typing import Dict, List, Any, Optional

LINEAR_API_URL = "https://api.linear.app/graphql"

class LinearClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("LINEAR_API_KEY")
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key if self.api_key else ""
        }

    async def _query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self.api_key:
            raise ValueError("LINEAR_API_KEY is not set.")
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                json={"query": query, "variables": variables},
                headers=self.headers
            )
            if response.status_code == 400:
                print(f"DEBUG: 400 Bad Request details: {response.text}")
            response.raise_for_status()
            result = response.json()
            if "errors" in result:
                raise Exception(f"Linear API error: {result['errors'][0]['message']}")
            return result["data"]

    async def get_me(self) -> Dict[str, Any]:
        query = """
        query {
          viewer {
            id
            name
            email
          }
        }
        """
        return await self._query(query)

    async def get_projects(self) -> List[Dict[str, Any]]:
        query = """
        query {
          projects {
            nodes {
              id
              name
            }
          }
        }
        """
        data = await self._query(query)
        return data["projects"]["nodes"]

    async def get_issues(self) -> List[Dict[str, Any]]:
        query = """
        query {
          issues {
            nodes {
              id
              identifier
              title
              priority
              state {
                name
              }
              assignee {
                id
                name
                avatarUrl
              }
              estimate
            }
          }
        }
        """
        data = await self._query(query)
        return data["issues"]["nodes"]
