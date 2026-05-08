const { defineConfig } = require("cypress");

module.exports = defineConfig({
  e2e: {
    baseUrl: process.env.QA_UI_URL || "http://127.0.0.1:5173",
    video: false,
    specPattern: "cypress/e2e/**/*.cy.js",
  },
});
