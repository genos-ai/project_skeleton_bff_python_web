# 08 - LLM Integration (Optional Module)

*Version: 1.0.0*
*Author: Architecture Team*
*Created: 2025-01-27*

## Changelog

- 1.0.0 (2025-01-27): Initial generic LLM integration standard

---

## Module Status: Optional

This module is **optional**. Adopt when your project:
- Integrates AI/LLM capabilities
- Uses generative AI for content creation
- Implements AI agents or assistants
- Requires natural language processing

For applications without AI features, this module is not required.

---

## Provider Selection

### Choosing a Provider

Select an LLM provider based on:
- Task complexity requirements
- Context window needs
- Cost constraints
- Latency requirements
- Data privacy requirements

### Common Providers

| Provider | Strengths | Considerations |
|----------|-----------|----------------|
| Anthropic (Claude) | Reasoning, safety, large context | Cost at scale |
| OpenAI (GPT) | Broad capabilities, ecosystem | Rate limits |
| Google (Gemini) | Multimodal, large context | Newer ecosystem |
| Local models | Privacy, no API costs | Hardware requirements |

### Model Tiers

Most providers offer model tiers:

| Tier | Use For |
|------|---------|
| Fast/Small | Classification, simple extraction, formatting |
| Standard | Code generation, analysis, conversations |
| Advanced | Complex reasoning, multi-step problems |

Match model tier to task complexity.

---

## Integration Architecture

### LLM Service Layer

All LLM calls go through a centralized service:

Responsibilities:
- Model selection
- Prompt construction
- API call execution
- Response parsing
- Cost tracking
- Error handling and retry

No direct provider API calls outside this service.

### Request Flow

1. Application code calls LLM service with task type and inputs
2. Service selects appropriate model
3. Service constructs prompt from template + inputs
4. Service calls provider API
5. Service parses and validates response
6. Service records usage for cost tracking
7. Service returns structured result to caller

### Timeout Configuration

Configure timeouts based on model characteristics:

| Model Tier | Suggested Timeout |
|------------|-------------------|
| Fast/Small | 30 seconds |
| Standard | 60 seconds |
| Advanced | 120 seconds |

Timeouts are per-request. Long operations should be broken into multiple calls.

---

## Prompt Management

### Prompt Storage

Store prompts in configuration files, not code:

```
config/
└── prompts/
    ├── tasks/
    │   ├── summarization.yaml
    │   ├── classification.yaml
    │   └── extraction.yaml
    └── shared/
        └── common_instructions.yaml
```

### Prompt Structure

Each prompt file contains:
- System prompt (role and behavior)
- Task-specific instructions
- Input placeholders
- Output format specification
- Example inputs/outputs (for few-shot)

### Prompt Versioning

Prompt files are version controlled. Changes to prompts require:
1. Version increment in file
2. Testing against evaluation set
3. Review before deployment

### Variable Injection

Prompts use placeholder syntax: `{{variable_name}}`

Variables injected at runtime:
- User input
- Context data
- Configuration values

No string concatenation for prompt construction. Always use template engine.

---

## Context Management

### Context Window Strategy

Large context windows are available but costs scale with token usage:

Strategy:
- Include only relevant context
- Summarize long documents
- Use retrieval to find relevant snippets
- Truncate conversation history intelligently

### Context Priority

When context must be reduced, prioritize:
1. Current user request (never truncate)
2. Most recent conversation turns
3. Directly relevant documents
4. Related context
5. Historical context (oldest first to remove)

---

## Response Handling

### Structured Outputs

Request structured outputs (JSON) when processing results programmatically:
- Specify exact schema in prompt
- Use JSON mode if available
- Validate response against schema
- Handle parse failures gracefully

### Response Validation

All LLM responses validated before use:
- Schema validation for structured outputs
- Sanity checks for generated code
- Safety checks for user-facing content

Invalid responses:
- Log full response for debugging
- Retry with clarified prompt (once)
- Fall back to error state if retry fails

### Streaming Responses

For user-facing chat:
- Stream response tokens as they arrive
- Display incremental output
- Allow cancellation mid-stream

For background processing:
- Wait for complete response
- No streaming (simpler error handling)

---

## Cost Management

### Cost Tracking

Every LLM call records:
- Model used
- Input tokens
- Output tokens
- Computed cost
- User/project association
- Task type

Storage: Database table for analysis and billing.

### Cost Controls

Implement limits at multiple levels:
- Per-request token limit
- Per-user daily/monthly limit
- Per-project budget
- System-wide circuit breaker

Exceeding limits:
- Soft limit: Warning, continue
- Hard limit: Reject request with clear message

### Cost Optimization

- Use smaller models for simple tasks
- Cache common prompts
- Summarize long contexts
- Batch related requests when possible

---

## Error Handling

### Retry Strategy

Transient errors (rate limits, timeouts, server errors):
- Retry with exponential backoff
- Maximum 3 retries

Permanent errors (invalid API key, malformed request):
- No retry
- Log and surface to caller

### Fallback Behavior

If LLM service unavailable:
- Operations requiring LLM fail with clear error
- No silent degradation that produces incorrect results
- Queue non-urgent requests for later processing if appropriate

### Rate Limiting

Implement client-side rate limiting:
- Track requests per minute
- Queue requests when approaching limits
- Spread requests over time window

### Circuit Breaker

Prevent cascade failures when provider is experiencing issues.

**States:**
```
CLOSED ──(failures exceed threshold)──> OPEN
   ^                                      |
   |                                      |
   └──(test succeeds)── HALF_OPEN <──(timeout)──┘
```

**Configuration:**

| Parameter | Value |
|-----------|-------|
| Failure threshold | 5 |
| Failure window | 60 seconds |
| Open duration | 30 seconds |
| Half-open max requests | 1 |

---

## Testing

### Prompt Testing

All prompts have evaluation sets:
- Representative inputs
- Expected output characteristics
- Automated scoring (where applicable)

Run evaluation on:
- Prompt changes
- Model version changes
- Regular intervals (catch model behavior drift)

### Mock Mode

Development and testing can use mock LLM responses:
- Predefined responses for known inputs
- Configurable via environment variable
- Never enabled in production

### Cost in Testing

Test environments use smallest viable models. Advanced models only used in production for designated complex tasks.

---

## Multi-Agent Systems (Optional)

### Agent Definition

Each agent has:
- Unique system prompt defining role
- Specific task types it handles
- Context requirements
- Output formats

### Agent Coordination

Agents communicate through the backend, not directly:
- Central orchestrator assigns tasks
- Agents receive context from orchestrator
- Agents return results to orchestrator
- Orchestrator synthesizes and routes

### Shared Context

Agents share context through:
- Project context service
- Redis for ephemeral shared state
- Database for persistent knowledge

No direct agent-to-agent messaging. All coordination through orchestrator.

---

## Adoption Checklist

When adopting this module:

- [ ] Select LLM provider(s)
- [ ] Implement LLM service layer
- [ ] Set up prompt storage and versioning
- [ ] Implement cost tracking
- [ ] Configure rate limiting
- [ ] Set up circuit breaker
- [ ] Create evaluation datasets for prompts
- [ ] Implement mock mode for testing
- [ ] Configure cost alerts and limits

### Optional Components

**Multi-Agent:**
- [ ] Define agent types and roles
- [ ] Implement orchestrator
- [ ] Set up shared context mechanism
- [ ] Configure agent-to-orchestrator communication
