# System Architecture Specification

## 1 Overview

This document describes the high-level architecture of a distributed document processing
pipeline: request ingestion, parsing, retrieval, and response generation.

## 2 System Architecture

### 2.1 High-Level Diagram

The pipeline is composed of five cooperating services, each independently deployable and
horizontally scalable behind a shared API gateway.

### 2.2 Component Summary

A brief overview of each major component in the system.

| Component | Description |
| --- | --- |
| API Gateway | Single entry point for all client requests. Handles routing, rate limiting, and request/response transformation. |
| Auth Service | Issues and validates JWT/OAuth2 tokens for every incoming request. |
| Document Parser | Normalizes PDF, DOCX, EPUB, and Markdown into one internal block model. |
| Vector Store | Stores embeddings for semantic retrieval across the document corpus. |
| Orchestrator | Coordinates multi-step requests across the parser and retrieval layers. |

## 3 Request Routing

Every request begins at the gateway, which authenticates it before dispatching to the
appropriate downstream service.

```python
class RequestRouter:
    def route(self, request: Request) -> Response:
        if not self.auth.validate(request.token):
            raise Unauthorized()

        handler = self.registry.resolve(request.path)
        return handler.handle(request)
```

## 4 Data Flow

1. Client sends a request through the API Gateway.
2. The gateway validates the request against the Auth Service.
3. The Document Parser normalizes the target document into blocks.
4. The Orchestrator retrieves relevant chunks from the Vector Store.
5. A response is assembled and returned to the client.

## 5 Notes and Considerations

> Every component in this system is stateless except for the Vector Store, which is the
> only service that owns durable state. This keeps horizontal scaling straightforward for
> everything else in the pipeline.

Future work includes adding a caching layer between the gateway and the parser to avoid
re-processing documents that have not changed on disk.
