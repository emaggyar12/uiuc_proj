You are building the frontend for my college basketball roster-construction / transfer-portal analytics website.

Reference site:
https://collegebasketballportal.com/

Goal:
Recreate the full frontend experience and navigation flow of the reference site using dummy data, while keeping the implementation legally distinct. Use the reference for layout structure, user flow, component hierarchy, table/filter behavior, simulator flow, and dashboard interactions. Do not copy proprietary branding, logos, exact text, unique assets, or private data.

Important:
Explore the website yourself in the browser before coding. Click through every major button, tab, filter, table row, player card, and navigation item. Specifically inspect:
- Main dashboard / all players view
- “In Portal” view or toggle
- Player expanded/profile views
- Portal Simulator
- Team selection flows
- Any roster-building or simulation screens
- Filters, sorting, search, dropdowns, badges, cards, and responsive behavior

Known reference behavior:
The site is a men’s college basketball transfer portal dashboard for the 2026-27 season, with BPR, NIL, and transfer projections. Search result snippets describe “All Players,” “In Portal,” filters, and portal-related dashboard behavior. The creator has also described an All Players / In Portal toggle, portal badges, portal status detail, and a Portal Simulator that can pre-populate departures and allow roster filling from confirmed portal entrants.

Tech stack:
- Next.js
- TypeScript
- Tailwind CSS
- Local mock data first
- No backend required yet

Architecture requirements:
- Do not hard-code player/team data inside components.
- Put mock data in `/data`.
- Put data-access functions in `/lib`.
- Build reusable components in `/components`.
- Pages should be easy to connect later to a Python/ML backend.

Core pages to build:
1. Dashboard / Player Leaderboard
   - Table of all players
   - Search bar
   - Filters for team, position, class, portal status, conference, projected BPR, NIL placeholder, playtype
   - Toggle between “All Players” and “In Portal”
   - Sortable columns
   - Expandable player rows/cards

2. Player Detail / Expanded Player Card
   - Player name, position, height, weight, class, current team
   - Previous team / new team fields
   - Portal status: not in portal, entered, committed, enrolled
   - Projected BPR
   - Projected stats
   - Playtype probability distribution
   - Fit score placeholder
   - Scouting summary placeholder
   - Team-fit explanation placeholder

3. Portal Simulator
   - Select a team
   - Show current roster
   - Auto-mark portal departures using mock portal_status
   - Allow user to remove players from roster
   - Allow user to add transfers from available portal players
   - Track scholarship/roster count
   - Show projected team summary after additions
   - Show team needs by position/playtype
   - Show recommended additions ranked by mock fit score

4. In Portal Page/View
   - Dedicated filtered view of only portal players
   - Status filters: entered, committed, enrolled
   - Available/uncommitted toggle
   - Player ranking recalculated within portal-only pool

5. Team Page
   - Team roster
   - Returning players
   - Departures
   - Incoming transfers
   - Incoming freshmen placeholder
   - Projected lineup
   - Team needs panel

6. Recommendations Page
   - Rank transfers and recruits for selected team
   - Include fit score, projected role, projected minutes, projected BPR, playtype match
   - Use dummy explanations for now

Mock data fields:
- player_id
- player_name
- position
- height
- weight
- class_year
- current_team
- previous_team
- new_team
- conference
- portal_status
- is_in_portal
- committed_team
- projected_bpr
- projected_minutes
- projected_points
- projected_rebounds
- projected_assists
- nil_value_placeholder
- playtype_probabilities
- fit_score
- recommendation_rank
- fit_explanation
- scouting_summary

Implementation notes:
- Make it polished and responsive.
- Prioritize functionality over perfect styling first.
- Use realistic dummy college basketball data.
- Add comments wherever real model/API data should later replace mock data.
- Create a clean README explaining how to run the app and where to replace mock data.
