'use strict';
/* Global application state — shared across all JS modules */
const State = {
  authEnabled:    true,
  authenticated:  false,
  sudo:           false,
  passwordSet:    false,
  cy:             null,
  rawGraph:       { nodes: [], edges: [] },
  rawEvents:      [],
  eventsView:     'timeline',   // 'timeline' | 'list'
  graphView:      'graph',      // 'graph' | 'list'
  graphDirection: false,        // true = show only edges from selected node
  eventsFilter:   '',           // current search string
  currentSummary: { groupId: null, date: null, content: '' },
  summaryEditing: false,
  currentPanel:   'landing',
  pagesLoaded:    new Set(),
  colorScheme:    'sky',        // active color preset
};
