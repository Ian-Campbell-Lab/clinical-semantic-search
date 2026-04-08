# Security and Data Governance

## Access Control Architecture

The reference deployment uses a layered access control model:

### Layer 1: Project-Level Isolation

Each research project receives its own containerized deployment of the
search application.  Containers are provisioned within the project's
existing cloud environment and inherit its IAM permissions.

### Layer 2: Note-Level Allowlisting

At application startup, the system queries the project's data tables to
build a sorted list of note IDs the project is authorized to access.
This list is written to a memory-mapped file for O(log n) lookups.

Every vector search result is checked against this allowlist before
note text is returned to the user.  Notes not in the project's
allowlist are silently filtered out.

### Layer 3: Audit Logging

Every query is logged with:
- User identity
- Query text and parameters (filters, MRN lists)
- Returned note IDs and MRNs
- Timestamp and request ID

Note text is **never** logged.  Logs are routed to a centralized
logging service for compliance review.

## PHI Considerations

The vector index itself does not contain PHI in a directly readable
form.  Embedding vectors are not reversible to source text.  However:

- **Metadata restricts** (MRN, author name) are stored as filterable
  attributes in the index.  These are PHI.
- **Note text** is stored in the metadata store (BigTable).  This is PHI.
- **The embedding model** is stored locally and does not contain PHI.

Access to the vector index endpoint and metadata store must be
restricted to authorized services via VPC networking and IAM.

## IRB Integration

At the reference institution, semantic search is registered as a
research tool with the IRB.  Individual research projects attach a
standardized protocol addendum describing their use of the search
system, including:

- The search queries they intend to run
- How results will be used in their research
- Data retention and destruction policies

This approach allows the search infrastructure to be shared across
projects while maintaining per-project IRB oversight.
