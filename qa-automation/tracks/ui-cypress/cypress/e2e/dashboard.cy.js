/// <reference types="cypress" />

const live = Cypress.env("UI_LIVE");

describe("Security lab dashboard", () => {
  before(function () {
    if (!live) {
      this.skip();
    }
  });

  it("shows the main heading", () => {
    cy.visit("/");
    cy.contains("h1", /AI Security Learning Lab/i).should("be.visible");
  });
});
