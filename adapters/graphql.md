# GraphQL API Adapter

## When to Use

- API endpoint is GraphQL (typically `POST /graphql`)
- Need nested or relational data that REST endpoints don't provide
- Discovered `/graphql`, `/api/graphql`, or `/gql` endpoint from page/source
- API provides introspection for schema discovery

## Discovery

1. **Endpoint check**: Test common paths:
   - `/graphql`
   - `/api/graphql`
   - `/gql`

2. **Introspection query** (if enabled):
   ```graphql
   query IntrospectionQuery {
     __schema {
       queryType { name }
       types {
         name
         kind
         fields {
           name
           type { name kind ofType { name } }
           args { name type { name } }
         }
       }
     }
   }
   ```

3. **Interactive docs**: If GraphQL Playground, GraphiQL, or Apollo Explorer available, explore schema there.

## Query Workflow

1. **Introspect schema** if introspection is enabled
2. **Identify relevant types** and fields needed for your use case
3. **Build query** with only required fields (avoid `*` or over-fetching)
4. **Test with small pagination** values first (`first: 10` or `limit: 10`)
5. **Implement pagination** using cursor-based or offset-based pattern
6. **Handle errors**: Check `errors` array in response, handle `extensions` for rate limit info

## Pagination Patterns

**Relay-style (cursor-based)** — preferred for large datasets:
```graphql
query {
  items(first: 100, after: "cursor_value") {
    edges {
      node {
        id
        name
        createdAt
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
```

**Offset-style** — simpler, good for smaller datasets:
```graphql
query {
  items(limit: 100, offset: 0) {
    id
    name
    total
  }
}
```

## Safety

- **Read-only only**: Only use queries, never mutations
- **Rate limits**: Respect `X-RateLimit-*` headers or `extensions.rateLimit` in response
- **Introspection disabled**: Skip if server rejects introspection queries
- **Log all queries**: Record every query sent for debugging and compliance

## Output

- **Response format**: Flatten nested GraphQL responses to JSON for analysis
- **CSV conversion**: Flatten selected fields to CSV with headers matching field names
- **Schema documentation**: Save discovered types and relationships as reference
- **Query log**: Maintain file with all queries, variables, and responses for reproducibility
