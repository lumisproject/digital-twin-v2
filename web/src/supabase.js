import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://guzisgycwvgfcejpmcun.supabase.co'
const supabaseKey = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd1emlzZ3ljd3ZnZmNlanBtY3VuIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzA0MjM0MjEsImV4cCI6MjA4NTk5OTQyMX0.SIWGzOdhwjh9FTPWMRA5c0ys1p6bEetynLXLhEvkvR0'
export const supabase = createClient(supabaseUrl, supabaseKey)