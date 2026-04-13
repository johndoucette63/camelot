# Feature Specification: Device Enrichment & Auto-Identification

**Feature Branch**: `013-device-enrichment`  
**Created**: 2026-04-13  
**Status**: Draft  
**Input**: User description: "Multi-protocol device fingerprinting (mDNS, nmap OS/service, NetBIOS, SSDP) to automatically identify unknown devices on the LAN"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Passively Identify Devices via Network Advertisements (Priority: P1)

As a Camelot admin, I open the device inventory and see that most of my Apple devices, speakers, printers, and smart home gear are now automatically identified by name and type — without any manual annotation. The system passively listens for mDNS/Bonjour service advertisements on the network and uses them to populate device names and roles.

**Why this priority**: mDNS is the highest-value, lowest-cost discovery method. It runs passively (no active probing), identifies the most common home network devices (Apple, Sonos, printers, HomeKit), and provides both a friendly name and a service type that maps directly to a device role. This single capability eliminates the majority of "unknown" devices on a typical home network.

**Independent Test**: Can be fully tested by running the scanner and verifying that devices advertising mDNS services (e.g., an iPhone, AirPlay speaker, or network printer) appear in the inventory with their advertised name and an auto-assigned role.

**Acceptance Scenarios**:

1. **Given** a device on the LAN is advertising mDNS services (e.g., `_airplay._tcp`, `_ipp._tcp`), **When** the enrichment pass runs, **Then** the device record is updated with the mDNS-advertised friendly name and a role derived from the service type.
2. **Given** an Apple device advertises `Johns-iPhone._companion-link._tcp.local.`, **When** the mDNS name is parsed, **Then** the device's display name shows "Johns iPhone" (cleaned of service suffixes and underscores).
3. **Given** a device already has a user-set annotation or hostname, **When** mDNS data is collected, **Then** the mDNS name is stored but does not overwrite the existing higher-priority name.
4. **Given** the mDNS listener is running, **When** a new device joins the network and advertises services, **Then** the device is enriched on the next enrichment cycle without requiring a restart.

---

### User Story 2 - Fingerprint Unknown Devices with OS and Service Detection (Priority: P2)

As a Camelot admin, I see that devices which don't advertise via mDNS — such as Linux servers, Windows PCs, and miscellaneous IoT hardware — are identified through active OS and service fingerprinting. The system runs targeted scans on devices that still lack metadata after passive discovery, revealing their operating system, open services, and NetBIOS names.

**Why this priority**: Active fingerprinting fills the gap left by passive mDNS. Many devices (especially non-Apple, non-smart-home devices) don't advertise via mDNS. OS and service detection provides OS family, open ports, and NetBIOS hostnames, enabling identification of the remaining unknowns. It's P2 because it requires active network probing and is rate-limited to avoid disruption.

**Independent Test**: Can be tested by having a device with no mDNS advertisement on the network (e.g., a Linux server or Windows PC), running the enrichment cycle, and verifying the device record is updated with OS family, OS detail, open services, and optionally a NetBIOS name.

**Acceptance Scenarios**:

1. **Given** a device has no hostname and no OS information after the passive discovery pass, **When** the active fingerprint scan runs, **Then** the device record is updated with the detected OS family (e.g., "Linux", "Windows") and OS detail string.
2. **Given** a device has open services (e.g., SSH on port 22, HTTP on port 80), **When** the fingerprint scan completes, **Then** the detected services are stored and visible in the device record.
3. **Given** a Windows PC advertises a NetBIOS name, **When** the fingerprint scan includes NetBIOS name resolution, **Then** the NetBIOS name is stored and used as the device hostname if no DNS or mDNS hostname exists.
4. **Given** the active scan is rate-limited to a maximum of 5 devices per enrichment cycle, **When** more than 5 devices need fingerprinting, **Then** only 5 are scanned in this cycle and the remainder are queued for the next cycle.
5. **Given** a device has already been enriched and its IP has not changed, **When** the next enrichment cycle runs, **Then** the device is skipped (not re-scanned).

---

### User Story 3 - Auto-Classify Device Roles from Collected Data (Priority: P3)

As a Camelot admin, I see that devices are automatically assigned a meaningful role (e.g., "printer", "speaker", "server", "workstation") based on the enrichment data collected from all discovery methods. This replaces the generic "unknown" classification and makes the inventory immediately useful for understanding what each device is.

**Why this priority**: Classification is the synthesis step that turns raw enrichment data into actionable information. Without it, having mDNS names and OS data is useful but still requires the admin to mentally categorize each device. Auto-classification delivers the "at a glance" understanding that is the core promise of this feature.

**Independent Test**: Can be tested by enriching several devices via any discovery method and verifying that the classification engine assigns appropriate roles based on the collected data, while never overwriting user-set roles.

**Acceptance Scenarios**:

1. **Given** a device has mDNS service type `_ipp._tcp` or `_printer._tcp`, **When** classification runs, **Then** the device role is set to "printer".
2. **Given** a device has mDNS service type `_airplay._tcp` or vendor name "Sonos", **When** classification runs, **Then** the device role is set to "speaker".
3. **Given** a device has OS family "macOS" or "Windows" and no more specific classification, **When** classification runs, **Then** the device role is set to "workstation".
4. **Given** a device has an open RTSP port (554) or vendor name containing "camera", **When** classification runs, **Then** the device role is set to "camera".
5. **Given** a device already has a user-set role, **When** auto-classification runs, **Then** the user-set role is never overwritten.
6. **Given** a device is auto-classified, **When** the classification is stored, **Then** a confidence level (high/medium/low) and the classification source (e.g., "mDNS service type", "OS family", "vendor string") are recorded alongside the role.

---

### User Story 4 - Discover Devices via UPnP/SSDP (Priority: P4)

As a Camelot admin, I see that smart TVs, media players, and other UPnP-enabled devices are identified with their friendly names and model information, even if they don't advertise via mDNS or respond to OS fingerprinting.

**Why this priority**: SSDP/UPnP is a supplementary discovery protocol that catches devices (primarily media/entertainment devices) that other methods miss. It's lower priority because it overlaps with mDNS for many devices, but adds unique value for smart TVs, media streamers, and some IoT gear.

**Independent Test**: Can be tested by having a UPnP-capable device on the network (e.g., a smart TV or media player), running the enrichment cycle, and verifying the device record shows the UPnP friendly name and model information.

**Acceptance Scenarios**:

1. **Given** a UPnP device is active on the network, **When** the SSDP discovery runs, **Then** the device's UPnP friendly name, manufacturer, and model information are stored on the matching device record.
2. **Given** the SSDP discovery has a timeout, **When** responses take too long, **Then** the discovery completes within a bounded time without blocking the overall enrichment cycle.
3. **Given** an SSDP response matches an existing device by IP, **When** the data is stored, **Then** it is merged with the existing record (not duplicated).

---

### User Story 5 - View Enrichment Data in Device Inventory (Priority: P5)

As a Camelot admin, I open the device inventory and see enrichment metadata — OS family, discovered names, classification confidence, and services — displayed alongside existing device information. Auto-classified roles are visually distinct from user-set roles so I can see at a glance which identifications are automatic vs. manual.

**Why this priority**: This is the presentation layer that makes all enrichment data visible and actionable. It depends on enrichment data existing (P1-P4) to be meaningful, but without it the enrichment work is invisible to the user.

**Independent Test**: Can be tested by navigating to the device inventory after enrichment has run and verifying that new columns and detail views display enrichment metadata correctly.

**Acceptance Scenarios**:

1. **Given** devices have been enriched with OS data, **When** the admin views the device table, **Then** an "OS" column displays the OS family for each device (or "—" if unknown).
2. **Given** a device has been auto-classified, **When** the admin views the device table, **Then** the role is visually distinguished from user-set roles (e.g., with an "auto" badge or italic styling).
3. **Given** a device has enrichment metadata (mDNS name, SSDP model, NetBIOS name, open services), **When** the admin clicks or expands a device row, **Then** all enrichment fields are displayed in a grouped "Identification" section.

---

### User Story 6 - Trigger Re-Enrichment for a Specific Device (Priority: P6)

As a Camelot admin, I notice a device's enrichment data is stale or incomplete. I click a "Re-scan" button on that device's row, and the device is re-enriched on the next scan cycle — picking up any changes in its network advertisements or services.

**Why this priority**: This is a convenience feature for edge cases where automatic enrichment didn't capture everything or device configuration has changed. Most devices will be correctly enriched automatically, making this a low-frequency action.

**Independent Test**: Can be tested by clicking the re-scan button on a device and verifying that the device is re-enriched on the next scan cycle, even if it was previously enriched.

**Acceptance Scenarios**:

1. **Given** a device has been previously enriched, **When** the admin clicks "Re-scan" on that device's row, **Then** the device is marked for re-enrichment and picked up in the next enrichment cycle.
2. **Given** a device's IP address has changed since its last enrichment, **When** the next enrichment cycle runs, **Then** the device is automatically re-enriched without manual intervention.

---

### Edge Cases

- What happens when a device is discovered by multiple protocols with conflicting names? The system uses a defined priority chain: user annotation > DNS hostname > mDNS name > NetBIOS name > SSDP friendly name. All source values are preserved in their respective fields so no data is lost.
- What happens when a device goes offline between the ARP sweep and the enrichment pass? The enrichment attempt for that device times out gracefully and the device retains whatever data was previously collected. It is retried on the next cycle.
- What happens when no enrichment protocols return any data for a device? The device retains its existing record with null enrichment fields and remains classified as "unknown". It is retried on subsequent cycles.
- What happens when the mDNS listener accumulates stale entries for devices that have left the network? mDNS entries are matched to devices by IP; if the IP no longer appears in the ARP sweep, the stale mDNS data is not applied.
- What happens when an active fingerprint scan takes too long on an unresponsive host? Each host has a per-host timeout (30 seconds) to prevent one slow device from blocking the entire enrichment cycle.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run an enrichment pass after each ARP sweep completes, targeting devices that lack metadata (no hostname, no OS family, or no enrichment timestamp).
- **FR-002**: System MUST passively listen for mDNS/Bonjour service advertisements on the local subnet and cache discovered services in memory.
- **FR-003**: System MUST parse mDNS advertised names into clean, human-readable friendly names (stripping service type suffixes and formatting underscores).
- **FR-004**: System MUST map mDNS service types to device roles using a configurable mapping (e.g., `_ipp._tcp` to "printer", `_airplay._tcp` to "speaker", `_homekit._tcp` to "iot").
- **FR-005**: System MUST run active OS and service fingerprinting against devices that still lack hostname or OS information after passive discovery.
- **FR-006**: System MUST rate-limit active fingerprinting to a maximum of 5 devices per enrichment cycle.
- **FR-007**: System MUST apply a per-host timeout of 30 seconds during active fingerprinting to avoid blocking on unresponsive hosts.
- **FR-008**: System MUST discover NetBIOS names during active fingerprinting and use them as the hostname if no DNS or mDNS hostname exists.
- **FR-009**: System MUST send SSDP multicast queries and fetch UPnP device descriptions to extract friendly names, manufacturer, and model information.
- **FR-010**: System MUST apply SSDP discovery with a bounded timeout (10 seconds) to avoid blocking the enrichment cycle.
- **FR-011**: System MUST auto-classify device roles using a priority chain: mDNS service type > open ports > OS family > vendor string.
- **FR-012**: System MUST never overwrite a user-set role or annotation with auto-classified data.
- **FR-013**: System MUST store a classification confidence level (high/medium/low) and the source of classification alongside each auto-classified role.
- **FR-014**: System MUST skip re-enrichment for devices that have already been enriched unless (a) the device's IP has changed since last enrichment, or (b) a manual re-enrichment is triggered.
- **FR-015**: System MUST provide a per-device "re-scan" action that marks a device for re-enrichment on the next cycle.
- **FR-016**: System MUST store all enrichment data (OS family, OS detail, mDNS name, NetBIOS name, SSDP friendly name, SSDP model, classification source, enrichment timestamp, enrichment IP) on the device record.
- **FR-017**: System MUST resolve name conflicts using a defined priority chain: user annotation > DNS hostname > mDNS name > NetBIOS name > SSDP friendly name. All source values MUST be preserved in their respective fields.
- **FR-018**: System MUST display an "OS" column in the device inventory table showing the OS family.
- **FR-019**: System MUST visually distinguish auto-classified roles from user-set roles in the device inventory.
- **FR-020**: System MUST display all enrichment metadata in a detail/expandable view for each device, grouped under an "Identification" section.
- **FR-021**: Each enrichment source (mDNS, fingerprinting, SSDP) MUST operate independently — failure of one source MUST NOT prevent the others from contributing data.

### Key Entities

- **Device** (extended): The existing device record, augmented with enrichment fields — OS family, OS detail, mDNS name, NetBIOS name, SSDP friendly name, SSDP model, classification source, classification confidence, enrichment timestamp, and enrichment IP.
- **Device Role**: A classification label (e.g., printer, speaker, server, workstation, camera, iot, dns, unknown) assigned either by the user or by auto-classification. Includes the source of the classification and a confidence level.
- **Enrichment Source**: A conceptual grouping representing each discovery protocol (mDNS, fingerprint, SSDP). Each source independently contributes data that is merged onto the device record.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After enrichment runs, at least 70% of devices on the network that were previously showing "unknown" or blank hostname are identified with a meaningful name or role.
- **SC-002**: The enrichment pass completes within 5 minutes for a network of up to 50 devices, without disrupting the existing ARP sweep cycle.
- **SC-003**: Auto-classified device roles are correct for at least 80% of devices (validated by the admin reviewing the inventory after a full enrichment cycle).
- **SC-004**: No user-set annotations or roles are ever overwritten by the enrichment process (100% preservation rate).
- **SC-005**: Individual device enrichment data is visible in the inventory within one scan cycle after the device is first discovered.
- **SC-006**: The admin can trigger a re-scan for any device and see updated enrichment data after the next scan cycle completes.

## Assumptions

- The target network is a single subnet (192.168.10.0/24) as used by the existing ARP scanner. Multi-subnet discovery is out of scope.
- The scanner environment has sufficient privileges for mDNS multicast listening, SSDP multicast queries, and OS fingerprinting (root/elevated access).
- The existing device inventory and ARP scanning infrastructure (from F4.2) is operational and provides the device records that enrichment extends.
- Devices that are offline or unreachable during an enrichment cycle will be retried on subsequent cycles; there is no separate retry queue.
- DHCP lease table integration, SNMP polling, active mDNS probing, historical enrichment tracking, and ML-based classification are out of scope for this feature.
- The mDNS service-type-to-role mapping covers common home network device types; exotic or proprietary service types may not be auto-classified and will remain "unknown" until the mapping is extended or a user annotation is applied.
- The network contains fewer than 50 active devices, which is typical for a home network. Performance targets assume this scale.
