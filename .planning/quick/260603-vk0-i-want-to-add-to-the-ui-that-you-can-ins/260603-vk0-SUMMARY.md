---
status: complete
---

## Quick Task 260603-vk0: Add document log inspection UI

**Completed:** 2026-06-04

### What was done

- Added "Logs" tab button to navigation bar
- Added "View Logs" button to each document row in the Documents table (alongside delete)
- Added full log viewer with:
  - Document info header showing document ID and filename
  - Log entries table (Timestamp, Severity, Step, Message, Details)
  - Color-coded severity badges (info=blue, warning=amber, error=red)
  - Expandable JSON details viewer per log entry
  - Pagination controls (50 per page, matching backend)
- Added auto-polling (5s interval) for live log updates when the view is active
- Auto-polling stops when switching away from the Logs tab
- Back button returns to Documents tab
- Proper loading, empty, and error states for all scenarios
- Added CSS styles for severity badges, details toggle, and actions column layout

### Files modified

- `src/eth_pipeline/static/index.html` — added Logs tab UI and JavaScript logic

### Verification

- Logs tab renders with all states (loading, empty, data)
- Severity badges display with correct colors
- "View Logs" button in documents table navigates to logs for that document
- Pagination controls are functional
- Details toggle shows/hides JSON content
- Auto-polling starts when viewing logs for active docs, stops on tab switch
- Back button returns to documents correctly
