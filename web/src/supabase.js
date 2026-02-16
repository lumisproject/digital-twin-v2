import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://jpnmvszvkpfavzlzoxop.supabase.co'
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Impwbm12c3p2a3BmYXZ6bHpveG9wIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzExOTQ5MDQsImV4cCI6MjA4Njc3MDkwNH0.HYP-oS2gzV1kMjNbosh0w0TCsxg1mrt1dGw4YoJCrnU'
export const supabase = createClient(supabaseUrl, supabaseKey)