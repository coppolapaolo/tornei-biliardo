# Templates Directory - Community Platform UI

This directory contains Jinja2 templates for the American Pool community platform, organized to support both tournament features and broader community engagement.

## Architecture Overview

Templates follow a component-based architecture with Bootstrap 5 styling and responsive design principles.

## Template Organization

### Base Templates

#### `base.html` - Master Layout
**Purpose**: Main application layout and structure
- Navigation bar with role-based menus
- Bootstrap 5 integration
- Flash message handling
- JavaScript and CSS includes
- Responsive mobile layout
- User authentication state display

### Core Application Pages

#### `index.html` - Home Page
**Purpose**: Application landing page
- Public tournament listings
- Guest access functionality
- Recent activity overview

#### `login.html` - Authentication
**Purpose**: User login interface
- Login form with validation
- Registration link
- Password reset option

#### `register.html` - User Registration
**Purpose**: New user account creation
- Registration form with validation
- Role selection (player default)
- Terms and conditions

#### `reset.html` - Password Reset
**Purpose**: Password recovery functionality
- Reset request form
- Email verification flow

### Domain-Specific Templates

#### Admin Templates (`admin/`)
Administrative interface templates:

- **Competition Management**:
  - `campionato_list.html`: Tournament listing and management
  - `campionato_detail.html`: Detailed tournament view
  - `gara_detail.html`: Competition round management
  - `match_management.html`: Match administration

- **User Management**:
  - `user_list.html`: User administration
  - `director_requests.html`: Director promotion requests
  - `venue_management.html`: Location and venue control

- **System Administration**:
  - `admin_dashboard.html`: Administrative overview
  - `system_stats.html`: System-wide statistics

#### Player Templates (`player/`)
Community member interface templates:

- **Community Profile**:
  - `profile.html`: Member profile, preferences, and social settings
  - `statistics.html`: Personal statistics and community standing
  - `dashboard.html`: Community activity overview and social dashboard

- **Social Match System**:
  - `match_proposals.html`: Community match invitation system
  - `create_match_proposal.html`: Social match proposal creation
  - `individual_matches.html`: Casual game history and social matches

- **Community Participation**:
  - `competitions.html`: Available tournaments and community events
  - `registration.html`: Event registration and community engagement
  - `my_competitions.html`: Personal tournament and event history

#### Dashboard Templates (`dashboard/`)
Role-specific dashboard components:
- `admin_dashboard.html`: Administrative overview
- `director_dashboard.html`: Director-specific tools
- `player_dashboard.html`: Player personal dashboard

#### Public Templates (`public/`)
Guest-accessible templates:
- `public_competitions.html`: Public competition listings
- `public_statistics.html`: General tournament statistics

### Component Templates (`components/`)

Reusable UI components using Bootstrap 5:

#### Administrative Components
- `_admin_campionato_cards.html`: Tournament management cards
- `_admin_dashboard_content.html`: Admin dashboard widgets
- `_admin_new_campionato_modal.html`: Tournament creation modal
- `_admin_empty_state.html`: Empty state messaging

#### Competition Components
- `_campionato_cards.html`: Tournament display cards
- `_campionato_details_info.html`: Tournament information
- `_campionato_general_classification.html`: Tournament rankings
- `_campionato_garas.html`: Tournament rounds listing
- `_available_garas.html`: Available competitions for registration
- `_available_proofs.html`: Available standalone competitions

#### Match Components
- `_match_cards.html`: Match display cards
- `_match_detail_card.html`: Detailed match information
- `_match_results_table.html`: Match results display
- `_rack_scoring_component.html`: Rack-level scoring interface

#### Matchmaking System Components
- `_amalfi_system.html`: Matchmaking strategy interface
- `_amalfi_preview_modal.html`: Strategy pairing preview modal
- `_amalfi_algorithm_info.html`: Strategy explanation and selection
- `_strategy_selector.html`: Dynamic strategy selection component
- `_pairing_preview.html`: Universal pairing preview for all strategies

#### User Interface Components
- `_user_card.html`: User profile display
- `_user_statistics.html`: User statistics widget
- `_notification_list.html`: Notification display
- `_role_badge.html`: User role indicators

#### Navigation and Layout
- `_navbar.html`: Main navigation bar
- `_sidebar.html`: Sidebar navigation
- `_breadcrumb.html`: Breadcrumb navigation
- `_pagination.html`: Pagination controls

#### Forms and Modals
- `_form_errors.html`: Form validation error display
- `_confirmation_modal.html`: Action confirmation dialogs
- `_loading_spinner.html`: Loading state indicators

#### Status and Feedback
- `_status_badges.html`: Status indicator badges
- `_flash_messages.html`: Flash message display
- `_empty_state.html`: Empty state messaging
- `_error_page.html`: Error page layout

## UI Design Principles

### Bootstrap 5 Integration
- Responsive grid system
- Component-based styling
- Consistent spacing and typography
- Mobile-first design approach

### Accessibility
- Semantic HTML structure
- ARIA labels and descriptions
- Keyboard navigation support
- Color contrast compliance

### User Experience
- Intuitive navigation patterns
- Clear visual hierarchy
- Consistent interaction patterns
- Responsive design for all devices

## Template Features

### Role-Based Display
Templates adapt content based on community member roles:
- **Guest**: Public community information and tournament listings
- **Player**: Personal data, social features, and community participation
- **Director**: Tournament organization and community leadership tools
- **Admin**: Full platform administration and community moderation

### Dynamic Content
- Real-time community activity updates
- Social interaction features
- AJAX-powered match coordination
- Live tournament standings and community leaderboards
- Community member presence and availability

### Form Handling
- Client-side validation
- Server-side error display
- Progressive enhancement
- Accessibility compliance

## JavaScript Integration

### Frontend Libraries
- Bootstrap 5 JavaScript components
- jQuery for DOM manipulation
- Chart.js for statistics visualization
- Custom JavaScript for matchmaking strategy handling
- Strategy-specific UI components

### AJAX Functionality
- Dynamic content updates
- Form submissions without page reload
- Real-time match scoring
- Live competition updates
- Strategy preview and selection
- Dynamic pairing generation for all strategies

## Internationalization

### Language Support
- Italian primary language
- English fallback for technical terms
- Consistent terminology throughout application
- Cultural context consideration

### Content Localization
- Date and time formatting
- Number formatting
- Currency display (where applicable)
- Regional competition rules

## Development Guidelines

### Template Creation
1. Extend from `base.html` for full pages
2. Use component includes for reusable elements
3. Follow Bootstrap 5 conventions
4. Implement proper accessibility features
5. Test responsive design across devices

### Component Design
1. Keep components focused and reusable
2. Use proper parameter passing
3. Implement error state handling
4. Include loading states where appropriate
5. Follow consistent naming conventions

### Best Practices
- Semantic HTML structure
- Proper form validation
- Accessibility compliance
- Mobile-responsive design
- Progressive enhancement
- SEO-friendly markup

### Testing Considerations
- Cross-browser compatibility
- Mobile device testing
- Accessibility validation
- Performance optimization
- User experience testing