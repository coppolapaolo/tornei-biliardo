# Routes Directory - Community Platform API

This directory contains Flask route handlers for the American Pool community platform, organized by domain and community member roles.

## Architecture Overview

Routes are organized using a RESTful approach with domain-based separation and role-based access control.

## Route Organization

### Core Route Files

#### `auth.py` - Authentication & Authorization
**Purpose**: User authentication and session management
- Login/logout functionality
- Session validation
- Role-based access control decorators

#### `main.py` - Public & General Routes
**Purpose**: Public-facing and general application routes
- Home page and public views
- Guest access functionality
- General information pages
- Public competition listings

#### `dashboard.py` - User Dashboard
**Purpose**: Personalized user interface
- Role-specific dashboard views
- User statistics and overview
- Quick actions and navigation

### Domain-Specific Routes

#### `player.py` - Community Member Features
**Purpose**: Community member functionality and social features
- Member profile management and social preferences
- Personal statistics and community standing
- Match proposals and community meetup organization
- Social match requests and networking
- Personal competition and casual game history
- Location preferences and availability for community games

**Community Features**:
- Social match proposal workflow
- Community member discovery
- Personal data privacy management
- Tournament and casual game registration
- Community engagement dashboard

#### `challenge.py` - Challenge System
**Purpose**: Skill challenges and attempts
- Challenge creation and management
- Challenge attempts tracking
- Challenge favorites system
- Skill assessment workflows

#### `individual_match.py` - Community Matches
**Purpose**: Community-driven casual match management
- Social match execution and coordination
- Detailed scoring for skill development
- Community match result sharing
- Social gaming history and statistics

#### `rating.py` - Rating System
**Purpose**: Player rating and handicap management
- Rating calculations
- Handicap rule management
- Category assignments
- Rating history tracking

#### `director.py` - Director Functions
**Purpose**: Tournament director capabilities
- Competition creation permissions
- Director-specific tools
- Enhanced tournament management

### Administrative Routes (`admin/`)

Administrative functionality is organized into specialized modules:

#### `admin/campionato.py` - Tournament Management
**Purpose**: Multi-round tournament administration
- Campionato creation and configuration
- Round scheduling and management
- Tournament-wide statistics
- Multi-competition coordination

#### `admin/competition.py` - Competition Management
**Purpose**: Individual competition (Gara) administration
- Competition creation and setup
- Player registration management
- Round execution and monitoring
- Match assignment and results
- Amalfi algorithm integration
- Competition completion workflows

**Key Features**:
- Matchmaking strategy preview system (all strategies supported)
- Idempotent round creation
- Inscription management with waitlist support
- Competition cancellation with participant notifications
- Multi-strategy support (Amalfi, Round-Robin, Elimination, Random)

#### `admin/match.py` - Match Administration
**Purpose**: Match-level administrative controls
- Match result validation
- Rack scoring management
- Match status modifications
- Administrative overrides

#### `admin/user.py` - User Administration
**Purpose**: User account and permission management
- User creation and modification
- Role assignments (player → director → admin)
- Director request approvals
- Account deactivation/reactivation

#### `admin/venue.py` - Venue Management
**Purpose**: Location and venue administration
- Billiard hall management
- Venue manager assignments
- Location-based permissions
- Venue request approvals

#### Administrative Dashboard
**Purpose**: System overview and administration (handled in general `dashboard.py`)
- Role-based dashboard routing (Admin/Director/Player)
- System-wide statistics and administrative quick actions
- User management overview and competition monitoring

## Request Handling Patterns

### Authentication & Authorization
- `@login_required`: Ensures user authentication
- `@admin_required`: Restricts to admin users
- `@director_required`: Allows directors and admins
- Role validation in route handlers

### Data Validation
- Form validation using Flask-WTF
- JSON payload validation
- Business rule validation
- Error handling with user-friendly messages

### Response Patterns
- JSON responses for AJAX requests
- Template rendering for page requests
- Flash messages for user feedback
- Proper HTTP status codes

### Error Handling
- Try-catch blocks for database operations
- Graceful degradation for failures
- User-friendly error messages
- Logging for debugging

## Matchmaking Strategy Integration

### Strategy Selection
Routes support dynamic strategy selection:
- **Strategy Configuration**: Admin/Director selects from available strategies
- **Preview Mode**: All strategies support pairing preview without database persistence
- **Runtime Switching**: Strategy can be changed between rounds (with validation)
- **Custom Policies**: Each strategy supports configurable policies for edge cases

### Strategy-Specific Endpoints
- **Amalfi**: Anti-rematch pairing with classification-based matching
- **Round-Robin**: Complete tournament generation with scheduling
- **Elimination**: Bracket generation and advancement logic
- **Random**: Balanced random pairing with conflict avoidance

## Key Route Functionalities

### Community Activities

#### Tournament Workflow
1. **Creation**: Community leaders create tournaments with strategy selection
2. **Configuration**: Set format, venue, dates, and community rules
3. **Registration**: Community members register with optional entry fees
4. **Execution**: Selected strategy creates fair pairings for all skill levels
5. **Community Engagement**: Real-time tracking and social interaction
6. **Completion**: Results sharing and community recognition

#### Casual Match Flow
1. **Proposal**: Members propose matches to individuals or community
2. **Discovery**: Location-based match finding and community connections
3. **Coordination**: Social scheduling and venue coordination
4. **Execution**: Casual gameplay with optional scoring
5. **Social Sharing**: Results and experience sharing within community

### Match Management
1. **Assignment**: Automatic via Amalfi or manual
2. **Execution**: Real-time scoring
3. **Validation**: Result confirmation
4. **Statistics**: Performance tracking

### User Management
1. **Registration**: Account creation
2. **Profile**: Personal information management
3. **Roles**: Permission escalation requests
4. **Activity**: Competition participation tracking

## Security Considerations

### Data Protection
- Personal data encryption/decryption
- Role-based access restrictions
- Input sanitization and validation
- CSRF protection

### Permission Levels
- **Guest**: Public view access only
- **Player**: Personal data and competition participation
- **Director**: Competition creation and management
- **Admin**: Full system access and user management

## API Design

### RESTful Conventions
- GET: Data retrieval
- POST: Resource creation
- PUT/PATCH: Resource updates
- DELETE: Resource removal

### Response Formats
- HTML templates for page views
- JSON for AJAX requests
- Appropriate status codes
- Consistent error message format

## Development Guidelines

### Route Creation
1. Choose appropriate domain file
2. Use descriptive route names
3. Implement proper authentication
4. Add comprehensive error handling
5. Include logging for debugging

### Security Best Practices
- Always validate user permissions
- Sanitize all input data
- Use proper error handling
- Log security-relevant events
- Implement rate limiting where needed

### Testing Considerations
- Create test cases for all routes
- Test authentication and authorization
- Validate error handling
- Check edge cases and boundary conditions
- Test with different user roles