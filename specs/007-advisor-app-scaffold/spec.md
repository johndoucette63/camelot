# Feature Specification: Network Advisor Application Scaffold

**Feature Branch**: `007-advisor-app-scaffold`  
**Created**: 2026-04-08  
**Status**: Draft  
**Input**: User description: "Scaffold FastAPI backend, React frontend, PostgreSQL database, and Docker Compose orchestration for the Network Advisor application"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Single-Command Application Deployment (Priority: P1)

As a Camelot administrator, I want to start the entire Network Advisor application stack with a single command so that deployment is simple, repeatable, and requires no manual setup of individual components.

**Why this priority**: Without orchestration, no component can be accessed or tested in an integrated fashion. This is the foundation that makes all other stories usable together.

**Independent Test**: Can be fully tested by running the deployment command and verifying that all application components start, connect to each other, and become accessible from the Mac workstation.

**Acceptance Scenarios**:

1. **Given** the application source code is available on HOLYGRAIL, **When** the administrator runs the deployment command, **Then** the backend, frontend, and database all start and become reachable within 60 seconds.
2. **Given** all services are running, **When** the administrator accesses `advisor.holygrail` from the Mac workstation browser, **Then** the frontend loads and can communicate with the backend via the existing reverse proxy.
3. **Given** the application is running, **When** the administrator stops and restarts the stack, **Then** all previously stored data is preserved across restarts.
4. **Given** the application has not been deployed before, **When** the administrator runs the deployment command for the first time, **Then** all required databases, schemas, and configurations are initialized automatically.

---

### User Story 2 - Backend Health Verification (Priority: P2)

As a developer, I want the backend service to expose a health status endpoint so that I can verify the backend is running and ready to accept requests before building features on top of it.

**Why this priority**: The backend is the central component that the frontend communicates with and where all business logic will live. Confirming it works is the first step for any feature development.

**Independent Test**: Can be fully tested by sending a request to the health endpoint and confirming a successful response, independent of the frontend or any business logic.

**Acceptance Scenarios**:

1. **Given** the backend service is running, **When** a health check request is made, **Then** the service responds with a success status confirming it is operational.
2. **Given** the backend service is starting up, **When** the database is not yet available, **Then** the health check indicates the service is not ready.
3. **Given** the backend service is running, **When** a developer navigates the project structure, **Then** there are clearly organized directories for routing, data models, and application entry point.

---

### User Story 3 - Frontend Development Environment (Priority: P3)

As a developer, I want the frontend application to be set up with a development-ready structure and styling framework so that I can immediately begin building dashboard and chat UI components.

**Why this priority**: The frontend is the user-facing layer and must be scaffolded correctly so that UI features (dashboard, chat) can be built without rework.

**Independent Test**: Can be fully tested by loading the frontend in a browser, verifying the default page renders with styling applied, and confirming that the development mode supports live reloading for rapid iteration.

**Acceptance Scenarios**:

1. **Given** the frontend service is running in production mode, **When** a user accesses it via a browser, **Then** a styled default page loads successfully.
2. **Given** a developer is working locally, **When** they start the frontend in development mode, **Then** code changes are reflected in the browser without manual refresh.
3. **Given** the frontend is running, **When** it makes a request to the backend, **Then** the request is properly routed to the backend service without cross-origin issues.

---

### User Story 4 - Persistent Data Storage (Priority: P4)

As a developer, I want a persistent database available to the backend so that future features (device inventory, alerts, service catalog) have a reliable storage layer from day one.

**Why this priority**: The database is essential for all data-driven features but has no business logic in this scaffold phase. It just needs to exist, accept connections, and persist data.

**Independent Test**: Can be fully tested by connecting to the database, creating a table, inserting data, restarting the stack, and confirming the data survives.

**Acceptance Scenarios**:

1. **Given** the database service is running, **When** the backend attempts to connect, **Then** the connection succeeds with the configured credentials.
2. **Given** data has been written to the database, **When** the entire application stack is stopped and restarted, **Then** all previously stored data is intact.
3. **Given** the database is starting for the first time, **When** it initializes, **Then** the application database and user are created automatically with an initial schema and the 5 known Camelot network devices pre-populated.

---

### Edge Cases

- What happens when the database takes longer than expected to start? The backend should wait or retry connections rather than crashing.
- What happens when a required port is already in use on the host? The administrator should receive a clear error message identifying the conflicting port.
- What happens when the backend starts before the database is ready? The system should handle startup ordering gracefully so that components recover once dependencies become available.
- What happens when the frontend cannot reach the backend? The frontend should display a meaningful connection error rather than a blank page.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST start all application components (backend, frontend, database) from a single deployment command.
- **FR-002**: The backend MUST expose a health check endpoint that verifies both its own status and database connectivity before reporting healthy.
- **FR-003**: The backend MUST be structured with separate areas for routing, data models, and application configuration to support future feature development.
- **FR-004**: The frontend MUST serve a styled default landing page accessible via a web browser.
- **FR-005**: The frontend MUST support a development mode with live reloading for local iteration.
- **FR-006**: The frontend MUST route all backend requests through a proxy to avoid cross-origin issues.
- **FR-007**: The database MUST be created automatically on first deployment with a dedicated application user.
- **FR-008**: The database MUST persist all data across application restarts using durable storage.
- **FR-009**: An initial database schema MUST be applied automatically on first boot, including seed data for the 5 known Camelot network devices (HOLYGRAIL, Torrentbox, NAS, Pi-hole DNS, Mac Workstation).
- **FR-010**: All services MUST share a common network allowing them to communicate by service name.
- **FR-011**: The application MUST be configurable through environment variables for database connection details, external service URLs, and other deployment-specific settings.
- **FR-012**: The application MUST be accessible from the Mac workstation via the existing reverse proxy at a dedicated hostname (e.g., `advisor.holygrail`), consistent with other HOLYGRAIL services.

### Key Entities

- **Device**: Represents a network device (IP address, hostname, device type, status). Central entity for the network inventory.
- **Service**: Represents a running service on a device (service name, port, status, associated device). Tracks what each device runs.
- **Alert**: Represents a monitoring event or notification (severity, message, timestamp, associated device/service). Captures issues detected across the network.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new developer can deploy the full application stack in under 5 minutes with no manual configuration beyond cloning the repository.
- **SC-002**: The backend health endpoint responds successfully within 2 seconds of the backend becoming ready.
- **SC-003**: The frontend loads and renders in a browser within 3 seconds of first access.
- **SC-004**: Data written to the database survives a full application stop-and-restart cycle with zero data loss.
- **SC-005**: All three components (backend, frontend, database) reach a healthy running state within 60 seconds of starting the deployment command.
- **SC-006**: The application is reachable from the Mac workstation across the local network without any additional network configuration.

## Clarifications

### Session 2026-04-08

- Q: Should the advisor integrate with the existing Traefik reverse proxy or use direct port access? → A: Integrate with existing Traefik — accessible at `advisor.holygrail` (matches current infrastructure pattern).
- Q: Should the health endpoint be a shallow alive check or verify database connectivity? → A: Deep — backend checks its own status plus database connectivity before reporting healthy.
- Q: Should the initial schema include seed data for known network devices? → A: Yes — pre-populate the 5 Camelot network devices (HOLYGRAIL, Torrentbox, NAS, Pi-hole, Mac) so the scaffold has real data from day one.

## Assumptions

- The target deployment host (HOLYGRAIL) is already set up with a container runtime and GPU drivers (Phase 1 complete).
- This scaffold contains no business logic — it is a skeleton for subsequent Network Advisor features (F4.2+) to build upon.
- The sole user of this application in the near term is the Camelot administrator (single-user system); authentication is out of scope for this scaffold.
- The local LLM service (Ollama) is already deployed and accessible on the network; the scaffold only needs to accept its URL as a configuration value, not deploy it.
- The database schema for devices, services, and alerts is a starting point and will evolve as feature requirements are refined in later phases.
- The frontend will be built for desktop browser access from the Mac workstation; mobile responsiveness is out of scope for this scaffold.
