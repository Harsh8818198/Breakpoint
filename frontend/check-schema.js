import mongoose from "mongoose";
import Blueprint from "./src/lib/db/models/Blueprint.js";

async function checkSchema() {
  console.log("Blueprint resources path:", Blueprint.schema.path('resources'));
  console.log("Blueprint resources caster:", Blueprint.schema.path('resources').caster);
  console.log("Blueprint resources schema:", Blueprint.schema.path('resources').schema);
  process.exit(0);
}

checkSchema();
